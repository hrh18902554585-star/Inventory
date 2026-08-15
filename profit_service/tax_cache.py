# -*- coding: utf-8 -*-
"""税运缓存（全局共享 + 原子写）

内存 dict + RLock 并发保护，dirty 达到阈值时原子落盘（.tmp + os.replace）。
值结构: {amount, fee_details, fee_ok, msg}（与 engine.tax_cache 一致）
"""
import json
import os
import threading

# 模块级单例
_cache = {}
_lock = threading.RLock()
_dirty = 0
_hits = 0
_misses = 0
_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tax_cache.json")
FLUSH_THRESHOLD = 50  # dirty 达到该值触发写盘


def load_cache(path: str) -> None:
    """启动加载 JSON，文件缺失/损坏时忽略；并记住路径供后续写盘"""
    global _cache, _path
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _cache = {str(k): v for k, v in data.items()}
    except Exception:
        pass
    _path = path


def _write_locked(path: str) -> None:
    """原子写: 先写 .tmp 再 os.replace（调用方需持有锁）"""
    global _dirty
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    _dirty = 0


def get(key) -> dict | None:
    with _lock:
        return _cache.get(str(key))


def put(key, value: dict) -> None:
    """写入缓存并计数 dirty，RLock 保护"""
    global _dirty
    with _lock:
        _cache[str(key)] = value
        _dirty += 1


def flush_if_needed() -> None:
    """dirty >= N 或外部调用时原子写盘"""
    global _dirty
    with _lock:
        if _dirty >= FLUSH_THRESHOLD:
            _write_locked(_path)


def force_flush() -> None:
    """无条件原子写盘"""
    with _lock:
        _write_locked(_path)


def get_stats() -> dict:
    """返回 {size, hits, misses}"""
    with _lock:
        return {"size": len(_cache), "hits": _hits, "misses": _misses}


def hit(key) -> bool:
    """命中返回 True 且 hits++，未命中 misses++"""
    global _hits, _misses
    with _lock:
        if str(key) in _cache:
            _hits += 1
            return True
        _misses += 1
        return False
