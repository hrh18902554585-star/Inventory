# -*- coding: utf-8 -*-
"""配置表版本管理

- 单文件类型（cost/link/subsidy/sort）：configs/<type>/<name>_v<version>.xlsx，版本自增，保留 10 版
- promo（多文件）：平铺 configs/promo/，文件名 {店铺名}__{清洗名}_v<version>.xlsx（版本自增，同名不覆盖）
- 版本从文件名解析（无 meta.json，避免单点故障）
"""
import io
import os
import re
import time
from datetime import datetime

import openpyxl

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIGS_DIR = os.path.join(BASE_DIR, "data", "configs")

CONFIG_TYPES = {
    "cost": {"name": "成本表", "required": True, "multiple": False},
    "link": {"name": "产品链接汇总表", "required": True, "multiple": False},
    "promo": {"name": "推广报表", "required": True, "multiple": True},
    "subsidy": {"name": "官补映射表", "required": False, "multiple": False},
    "sort": {"name": "产品排序表", "required": False, "multiple": False},
}

MAX_VERSIONS = 10
_VER_RE = re.compile(r"^(?P<name>.+)_v(?P<ver>\d+)\.(?P<ext>csv|xlsx)$", re.IGNORECASE)

# 上传预检必要表头（sort 特殊：首列非空）
# 别名与 engine.load_* 的候选表头对齐（引擎为权威，契约表头必含）
_REQUIRED_HEADERS = {
    "cost": ["组合编码", "sku成本"],
    "link": ["店铺名称", "产品名称", "商品id"],
    "promo": ["商品ID", "总花费(元)"],
    "subsidy": ["链接id", "规格编码", "官补金额"],
}
_HEADER_ALIASES = {
    "cost": {"组合编码": ["组合编码", "商家编码-规格维度"], "sku成本": ["sku成本", "sku成本 "]},
    "link": {"店铺名称": ["店铺名称", "店铺"], "产品名称": ["产品名称", "产品"],
             "商品id": ["商品id", "商品ID", "链接id"]},
    "promo": {"商品ID": ["商品ID", "商品id", "链接id"], "总花费(元)": ["总花费(元)", "总花费", "花费"]},
    "subsidy": {"链接id": ["链接id", "商品ID", "商品id"],
                "规格编码": ["规格编码", "商家编码-规格维度"], "官补金额": ["官补金额"]},
}


def _clean_name(name: str) -> str:
    """清洗文件名：保留中文，剔除 \\/:*?"<>| 与控制符，拒绝 ..，限长 200"""
    name = os.path.basename(str(name).strip())
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name)
    name = name.replace("..", "_")
    return name[:200] or "配置表"


def _scan_dir(d: str) -> list:
    """扫描目录，返回 [(version, abs_path)]，按版本升序"""
    out = []
    if not os.path.isdir(d):
        return out
    for fn in os.listdir(d):
        m = _VER_RE.match(fn)
        if m:
            out.append((int(m.group("ver")), os.path.join(d, fn)))
    out.sort(key=lambda x: x[0])
    return out


def _file_path(base_dir: str, cfg_type: str, version) -> str | None:
    """取指定类型的指定版本绝对路径；不存在返回 None；版本号非法返回 None"""
    if version is None:
        return None
    try:
        version = int(version)
    except (TypeError, ValueError):
        return None
    for v, path in _scan_dir(os.path.join(base_dir, cfg_type)):
        if v == version:
            return path
    return None


def _current(base_dir: str, cfg_type: str) -> dict | None:
    """当前（最高版本）配置记录；无则 None"""
    files = _scan_dir(os.path.join(base_dir, cfg_type))
    if not files:
        return None
    v, path = files[-1]
    return _record(cfg_type, v, path)


def _record(cfg_type: str, version: int, path: str) -> dict:
    return {
        "type": cfg_type,
        "version": version,
        "filename": os.path.basename(path),
        "size": os.path.getsize(path),
        "uploaded_at": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S"),
        "path": os.path.abspath(path),
    }


def validate_on_upload(cfg_type, file_storage) -> (bool, str):
    """上传预检：openpyxl 可打开 + 必要表头（sort: 首列非空）"""
    if cfg_type not in CONFIG_TYPES:
        return False, "未知配置类型"
    file_storage.seek(0)
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_storage.read()), data_only=True)
    except Exception as e:
        return False, f"无法解析 Excel 文件: {e}"
    headers = []
    ws = wb.worksheets[0] if wb.worksheets else None
    if ws is not None:
        for row in ws.iter_rows(min_row=1, max_row=1, values_only=True):
            headers = [str(h or "").strip() for h in row]
            break
    wb.close()
    if cfg_type == "sort":
        if not headers or not headers[0]:
            return False, "产品排序表首列不能为空"
        return True, "OK"
    lower = [h.lower() for h in headers]
    for req in _REQUIRED_HEADERS.get(cfg_type, []):
        aliases = [a.lower() for a in _HEADER_ALIASES.get(cfg_type, {}).get(req, [req])]
        if not any(a in lower for a in aliases):
            return False, f"缺少必要表头: {req}（当前表头: {[h for h in headers if h]}）"
    return True, "OK"


def save_config(cfg_type: str, file_storage) -> (bool, str | dict):
    """保存配置：单文件类型覆盖式版本化；promo 平铺；返回 (True, 记录) 或 (False, 文案)"""
    if cfg_type not in CONFIG_TYPES:
        return False, "未知配置类型"
    ok_v, msg = validate_on_upload(cfg_type, file_storage)
    if not ok_v:
        return False, msg
    d = os.path.join(CONFIGS_DIR, cfg_type)
    os.makedirs(d, exist_ok=True)
    base, ext = os.path.splitext(_clean_name(file_storage.filename or "配置表.xlsx"))
    ext = ext.lower() or ".xlsx"
    files = _scan_dir(d)
    version = (files[-1][0] + 1) if files else 1
    if cfg_type == "promo":
        try:
            from engine import extract_store_name
            store = extract_store_name(base + ext)
        except Exception:
            store = "未知店铺"
        prefix = f"{store}__" if store != "未知店铺" else ""
    else:
        prefix = ""
    filename = f"{prefix}{base}_v{version}{ext}"
    path = os.path.join(d, filename)
    file_storage.seek(0)
    file_storage.save(path)
    # 保留最近 10 版（promo 按店铺前缀分组清理）
    if cfg_type == "promo":
        groups = {}
        for fn in os.listdir(d):
            if _VER_RE.match(fn):
                groups.setdefault(fn.split("__")[0] if "__" in fn else "", []).append(fn)
        for key, fns in groups.items():
            fns.sort(key=lambda x: int(_VER_RE.match(x).group("ver")), reverse=True)
            for old in fns[MAX_VERSIONS:]:
                os.remove(os.path.join(d, old))
    else:
        for v, old_path in files[:-MAX_VERSIONS] if len(files) > MAX_VERSIONS else []:
            os.remove(old_path)
    return True, _record(cfg_type, version, path)


def list_configs() -> dict:
    """{type: {"current": {...} 或 None, "versions": [...]}}，版本降序"""
    out = {}
    for cfg_type, meta in CONFIG_TYPES.items():
        files = _scan_dir(os.path.join(CONFIGS_DIR, cfg_type))
        versions = [_record(cfg_type, v, p) for v, p in files]
        versions.reverse()
        current = None if meta["multiple"] or not versions else versions[0]
        out[cfg_type] = {"current": current, "versions": versions}
    return out


def delete_config(cfg_type: str, version: int | None) -> (bool, str):
    """删除配置：version 指定删该版；None 删当前（promo 删全部）"""
    if cfg_type not in CONFIG_TYPES:
        return False, "未知配置类型"
    d = os.path.join(CONFIGS_DIR, cfg_type)
    if not os.path.isdir(d):
        return False, "配置不存在"
    if version is None:
        if CONFIG_TYPES[cfg_type]["multiple"]:
            for fn in list(os.listdir(d)):
                os.remove(os.path.join(d, fn))
            return True, "已删除全部推广报表"
        cur = _current(CONFIGS_DIR, cfg_type)
        if cur is None:
            return False, "配置不存在"
        os.remove(cur["path"])
        return True, "已删除当前版本"
    path = _file_path(CONFIGS_DIR, cfg_type, version)
    if path is None:
        return False, "配置版本不存在"
    os.remove(path)
    return True, "已删除"


def resolve_configs(versions: dict, base_dir: str | None = None) -> dict | tuple:
    """版本 → 绝对路径映射
    versions: {"cost": 2, "promo": [1,3], ...} → {"cost": 路径, "link": 路径, "promo": [路径], "subsidy": 路径|None, "sort": 路径|None}
    未指定版本取 current；required 缺失 → (None, "未上传必填配置: 成本表")
    """
    base = base_dir or CONFIGS_DIR
    result = {}
    for cfg_type, meta in CONFIG_TYPES.items():
        if meta["multiple"]:
            paths = []
            if cfg_type in versions and versions[cfg_type]:
                for v in versions[cfg_type]:
                    p = _file_path(base, cfg_type, v)
                    if p is not None:
                        paths.append(p)
            else:
                paths = [p for _, p in _scan_dir(os.path.join(base, cfg_type))]
            result[cfg_type] = paths
        else:
            p = None
            if cfg_type in versions and versions[cfg_type]:
                p = _file_path(base, cfg_type, versions[cfg_type])
            else:
                cur = _current(base, cfg_type)
                p = cur["path"] if cur else None
            result[cfg_type] = p
        if meta["required"] and not result[cfg_type]:
            return None, f"未上传必填配置: {meta['name']}"
    return result
