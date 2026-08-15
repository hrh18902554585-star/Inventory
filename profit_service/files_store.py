# -*- coding: utf-8 -*-
"""上传文件存储/快照/孤儿清理

- 订单文件：data/uploads/清洗名_时间戳.ext（永不覆盖），id = f_ + sha1(文件名)[:8]（可从文件名还原，无需 meta）
- 快照：任务创建时复制订单+配置到 data/tasks/<id>/inputs/
"""
import hashlib
import os
import re
import shutil
import time
from datetime import datetime

from configs import resolve_configs as _resolve_configs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "data", "uploads")

ALLOWED_EXT = {".csv", ".xlsx"}
MAX_SIZE = 10 * 1024 * 1024
_CTRL_RE = re.compile(r"[\x00-\x1f]")


def sanitize_filename(name: str) -> str:
    """保留中文，剔除 \\/:*?"<>| 控制符，拒绝 ..，限长 200"""
    name = os.path.basename(str(name).strip())
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = _CTRL_RE.sub("_", name)
    name = name.replace("..", "_")
    return name[:200] or "upload"


def validate_upload_file(file_storage) -> (bool, str):
    """扩展名白名单 .csv/.xlsx + 大小 ≤10MB + xlsx 魔数 PK\\x03\\x04"""
    filename = file_storage.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return False, f"不支持的文件类型: {ext or '未知'}（仅支持 .csv/.xlsx）"
    file_storage.seek(0, 2)
    size = file_storage.tell()
    file_storage.seek(0)
    if size > MAX_SIZE:
        return False, "文件超过 10MB 限制"
    if ext == ".xlsx":
        head = file_storage.read(4)
        file_storage.seek(0)
        if head[:4] != b"PK\x03\x04":
            return False, "xlsx 文件格式校验失败（魔数不符）"
    return True, "OK"


def _file_id(filename: str) -> str:
    """文件 id 由文件名哈希导出，保证重启后可还原"""
    return "f_" + hashlib.sha1(filename.encode("utf-8")).hexdigest()[:8]


def _record(path: str) -> dict:
    return {
        "id": _file_id(os.path.basename(path)),
        "name": os.path.basename(path),
        "size": os.path.getsize(path),
        "path": path,
        "uploaded_at": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S"),
    }


def _scan(dir_path: str) -> list:
    if not os.path.isdir(dir_path):
        return []
    return [_record(os.path.join(dir_path, fn)) for fn in os.listdir(dir_path)
            if os.path.isfile(os.path.join(dir_path, fn))]


def _find_in(dir_path: str, file_id: str) -> dict | None:
    for rec in _scan(dir_path):
        if rec["id"] == file_id:
            return rec
    return None


def find_order_file(file_id: str) -> dict | None:
    """按 id 查找上传文件记录"""
    return _find_in(UPLOADS_DIR, file_id)


def save_order_file(file_storage) -> dict | None:
    """磁盘: 清洗名_时间戳.ext；返回 {id, name, size, path, uploaded_at}"""
    ok_v, msg = validate_upload_file(file_storage)
    if not ok_v:
        return None
    orig = file_storage.filename or "upload.csv"
    clean = sanitize_filename(orig)
    base, ext = os.path.splitext(clean)
    if len(base) > 100:
        base = base[:100].rstrip(" .")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{base}_{stamp}{ext.lower()}"
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    path = os.path.join(UPLOADS_DIR, filename)
    try:
        file_storage.seek(0)
        file_storage.save(path)
    except OSError:
        return None
    return _record(path)


def list_order_files() -> list:
    """全部上传文件记录"""
    return _scan(UPLOADS_DIR)


def delete_order_file(file_id: str) -> (bool, str):
    rec = _find_in(UPLOADS_DIR, file_id)
    if rec is None:
        return False, "文件不存在"
    os.remove(rec["path"])
    return True, "已删除"


def snapshot_inputs(task_id, order_file_ids: list, configs: dict, uploads_dir, configs_dir, task_inputs_dir) -> dict | tuple:
    """复制订单+配置到 tasks/<id>/inputs/；返回 {"order_files": [路径], "configs": {绝对路径 dict}}
    订单文件不存在 → (None, error_str)
    """
    os.makedirs(task_inputs_dir, exist_ok=True)
    order_paths = []
    for fid in order_file_ids or []:
        rec = _find_in(uploads_dir, fid)
        if rec is None:
            return None, f"订单文件不存在或已删除: {fid}"
        dest = os.path.join(task_inputs_dir, os.path.basename(rec["path"]))
        shutil.copy2(rec["path"], dest)
        order_paths.append(dest)

    resolved = _resolve_configs(configs or {}, base_dir=configs_dir)
    if isinstance(resolved, tuple):
        return None, resolved[1]
    cfg_dir = os.path.join(task_inputs_dir, "configs")
    os.makedirs(cfg_dir, exist_ok=True)
    cfg_copy = {}
    for key, src in resolved.items():
        if key == "promo":
            paths = []
            for p in src or []:
                d = os.path.join(cfg_dir, os.path.basename(p))
                shutil.copy2(p, d)
                paths.append(d)
            cfg_copy[key] = paths
        elif src:
            d = os.path.join(cfg_dir, os.path.basename(src))
            shutil.copy2(src, d)
            cfg_copy[key] = d
        else:
            cfg_copy[key] = None
    return {"order_files": order_paths, "configs": cfg_copy}


def cleanup_orphans(max_age_days=7) -> list:
    """删除 .part 残留 + 全量扫描超龄上传文件"""
    removed = []
    if not os.path.isdir(UPLOADS_DIR):
        return removed
    for fn in os.listdir(UPLOADS_DIR):
        path = os.path.join(UPLOADS_DIR, fn)
        if not os.path.isfile(path):
            continue
        if fn.endswith(".part"):
            os.remove(path)
            removed.append(fn)
            continue
        age = time.time() - os.path.getmtime(path)
        if age > max_age_days * 86400:
            os.remove(path)
            removed.append(fn)
    return removed
