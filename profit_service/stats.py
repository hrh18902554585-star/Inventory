# -*- coding: utf-8 -*-
"""指标收集（全局共享 + 原子写）

内存 dict + RLock 并发保护，每次写操作后原子落盘（.tmp + os.replace）。
get_stats() 返回契约字段 + 派生字段（success_rate 等）。
"""
import json
import math
import os
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATS_FILE = os.path.join(BASE_DIR, "data", "stats.json")
MAX_DURATIONS = 50  # 保留最近 N 个任务耗时，用于 P95

_state = {
    "total_tasks": 0,
    "success": 0,
    "failed": 0,
    "durations": [],
    "api_calls": 0,
    "api_fails": 0,
    "cache_lookups": 0,
    "cache_hits": 0,
}
_lock = threading.RLock()


def _load_locked(data: dict) -> None:
    """合并磁盘数据与默认字段，兼容旧版本字段缺失（调用方需持有锁）"""
    merged = {
        "total_tasks": 0, "success": 0, "failed": 0, "durations": [],
        "api_calls": 0, "api_fails": 0, "cache_lookups": 0, "cache_hits": 0,
    }
    if isinstance(data, dict):
        merged.update(data)
    merged["durations"] = [float(x) for x in merged["durations"]][-MAX_DURATIONS:]
    _state.clear()
    _state.update(merged)


def _save() -> None:
    """原子写盘: 先写 .tmp 再 os.replace（调用方需持有锁）"""
    d = os.path.dirname(STATS_FILE) or "."
    os.makedirs(d, exist_ok=True)
    tmp = STATS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATS_FILE)


def load_stats(path: str = STATS_FILE) -> None:
    """启动加载 JSON，文件缺失/损坏时保持默认值"""
    global STATS_FILE
    STATS_FILE = path
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    with _lock:
        _load_locked(data)


def record_task_finish(ok: bool, duration_sec: float) -> None:
    """任务结束: total_tasks++，success/failed++，记录最近耗时"""
    with _lock:
        _state["total_tasks"] += 1
        if ok:
            _state["success"] += 1
        else:
            _state["failed"] += 1
        _state["durations"].append(float(duration_sec))
        _state["durations"] = _state["durations"][-MAX_DURATIONS:]
        _save()


def record_api_call(ok: bool) -> None:
    """税运接口调用: api_calls++，失败时 api_fails++"""
    with _lock:
        _state["api_calls"] += 1
        if not ok:
            _state["api_fails"] += 1
        _save()


def record_cache(hit: bool) -> None:
    """缓存查询: cache_lookups++，命中时 cache_hits++"""
    with _lock:
        _state["cache_lookups"] += 1
        if hit:
            _state["cache_hits"] += 1
        _save()


def _p95(durations: list) -> float:
    """排序取第 ceil(0.95*n) 位作为 P95"""
    if not durations:
        return 0.0
    n = len(durations)
    idx = max(0, math.ceil(0.95 * n) - 1)
    return sorted(durations)[idx]


def get_stats() -> dict:
    """返回统计字段 + 派生字段"""
    with _lock:
        durations = _state["durations"]
        n = len(durations)
        avg = sum(durations) / n if n else 0.0
        total = _state["total_tasks"]
        calls = _state["api_calls"]
        lookups = _state["cache_lookups"]
        return {
            "total_tasks": total,
            "success": _state["success"],
            "failed": _state["failed"],
            "avg_duration": round(avg, 3),
            "p95_duration": round(_p95(durations), 3),
            "api_calls": calls,
            "api_fails": _state["api_fails"],
            "cache_lookups": lookups,
            "cache_hits": _state["cache_hits"],
            "success_rate": round(_state["success"] / total, 4) if total else 0.0,
            "api_fail_rate": round(_state["api_fails"] / calls, 4) if calls else 0.0,
            "cache_hit_rate": round(_state["cache_hits"] / lookups, 4) if lookups else 0.0,
        }
