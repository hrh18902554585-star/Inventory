# -*- coding: utf-8 -*-
"""任务调度/状态机/日志

- 单例 ThreadPoolExecutor(MAX_CONCURRENT)，超出排队（DB pending 计数 ≤ MAX_QUEUED）
- run_job: pending→running→engine.process→done/error；日志/进度回调写库
- 税运缓存：任务结束后合并 engine 结果并 force_flush（全局共享）
"""
import json
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor

import configs
import db
import files_store
import stats
import tax_cache
from engine import EngineError, ProfitEngine
from logging_setup import attach_task_id, get_logger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_DIR = os.path.join(BASE_DIR, "data", "tasks")
OUTPUTS_DIR = os.path.join(BASE_DIR, "data", "outputs")

MAX_CONCURRENT = 2
MAX_QUEUED = 10

_executor = None
_logger = None


def init_task_manager() -> None:
    """ThreadPoolExecutor(2) + 中断任务标记"""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT)
    db.mark_interrupted_tasks()


def submit_job(params: dict) -> (str, str | None):
    """校验 → 建任务(pending) → 提交线程池；返回 (task_id, None) 或 (None, 错误文案)
    错误文案前缀约定: "参数错误:" code2 / "配置缺失:" code3 / "服务忙:" code6
    """
    global _executor
    if _executor is None:
        init_task_manager()
    cookie = str(params.get("cookie") or "").strip()
    order_files = params.get("order_files") or []
    if not cookie:
        return None, "参数错误: Cookie 不能为空"
    if not isinstance(order_files, list) or not order_files:
        return None, "参数错误: 至少选择一个订单文件"
    if len(db.list_tasks(status="pending")) >= MAX_QUEUED:
        return None, "服务忙: 排队任务已满（上限 10），请稍后再试"
    for fid in order_files:
        if files_store.find_order_file(fid) is None:
            return None, f"参数错误: 订单文件不存在或已删除: {fid}"
    resolved = configs.resolve_configs(params.get("configs") or {})
    if isinstance(resolved, tuple):
        return None, "配置缺失: " + resolved[1]
    task_id = db.create_task(params)
    try:
        _executor.submit(run_job, task_id)
    except RuntimeError:
        db.delete_task(task_id)
        return None, "服务忙: 任务调度失败，请稍后再试"
    return task_id, None


def get_job(task_id) -> dict | None:
    return db.get_task(task_id)


def list_jobs() -> list[dict]:
    return db.list_tasks()


def delete_job(task_id) -> (bool, str):
    """仅 done/error；删除任务记录 + outputs/tasks 目录"""
    task = db.get_task(task_id)
    if task is None:
        return False, "任务不存在"
    if task["status"] not in ("done", "error"):
        return False, "任务运行中，无法删除"
    db.delete_task(task_id)
    for d in (os.path.join(OUTPUTS_DIR, task_id), os.path.join(TASKS_DIR, task_id)):
        shutil.rmtree(d, ignore_errors=True)
    return True, "已删除"


def rerun_job(task_id) -> (str, str | None):
    """复用 params_json 重建任务（新 id）"""
    task = db.get_task(task_id)
    if task is None:
        return None, "任务不存在"
    return submit_job(task["params_json"])


def get_download_path(task_id, filename) -> str | None:
    """校验 filename 在 outputs/<id>/ 内且存在；任务须 done"""
    task = db.get_task(task_id)
    if task is None or task["status"] != "done":
        return None
    if os.path.basename(str(filename)) != str(filename) or str(filename) in ("", ".", ".."):
        return None
    path = os.path.join(OUTPUTS_DIR, task_id, str(filename))
    if os.path.isfile(path):
        return os.path.abspath(path)
    return None


def run_job(task_id) -> None:
    """pending→running→engine.process→done/error"""
    global _logger
    if _logger is None:
        _logger = get_logger()
    task = db.get_task(task_id)
    if task is None:
        return
    attach_task_id(task_id)
    params = task["params_json"]
    started = time.time()
    db.update_task(task_id, status="running", progress=0, status_text="任务开始...", error="")
    try:
        snap = files_store.snapshot_inputs(
            task_id,
            params.get("order_files") or [],
            params.get("configs") or {},
            files_store.UPLOADS_DIR,
            configs.CONFIGS_DIR,
            os.path.join(TASKS_DIR, task_id, "inputs"),
        )
        if isinstance(snap, tuple):
            raise EngineError(snap[1] or "快照输入失败", code=21000)
        outputs_dir = os.path.join(OUTPUTS_DIR, task_id)
        os.makedirs(outputs_dir, exist_ok=True)

        def log_cb(msg):
            db.append_log(task_id, {"level": "INFO", "msg": str(msg)})

        def progress_cb(pct, text):
            db.update_task(task_id, progress=float(pct), status_text=str(text))

        engine = ProfitEngine(log_cb=log_cb, progress_cb=progress_cb)
        exclude_ids = params.get("exclude_ids", "")
        if isinstance(exclude_ids, list):
            exclude_ids = ",".join(str(x) for x in exclude_ids)
        result = engine.process(
            order_files=snap["order_files"],
            configs=snap["configs"],
            cookie=params.get("cookie", ""),
            thread_count=params.get("thread_count", 2),
            enable_tax=params.get("enable_tax", True),
            exclude_ids=exclude_ids,
            output_dir=outputs_dir,
        )
        for key, value in (result.get("tax_cache") or {}).items():
            tax_cache.put(key, value)
        files = [os.path.basename(f) for f in result.get("files", [])]
        db.update_task(task_id, status="done", progress=100, status_text="处理完成",
                       result_files_json=json.dumps(files, ensure_ascii=False), finished_at=None)
        stats.record_task_finish(True, time.time() - started)
        _logger.info("任务 %s 完成，生成 %d 个文件", task_id, len(files))
    except Exception as e:
        _logger.error("任务 %s 失败: %s", task_id, e)
        db.update_task(task_id, status="error", status_text="处理失败", error=str(e), finished_at=None)
        stats.record_task_finish(False, time.time() - started)
    finally:
        try:
            tax_cache.force_flush()
        except Exception:
            pass


def cleanup_outputs(max_age_hours=24) -> None:
    """启动时清扫超龄输出目录"""
    if not os.path.isdir(OUTPUTS_DIR):
        return
    deadline = time.time() - max_age_hours * 3600
    for name in os.listdir(OUTPUTS_DIR):
        path = os.path.join(OUTPUTS_DIR, name)
        if os.path.isdir(path) and os.path.getmtime(path) < deadline:
            shutil.rmtree(path, ignore_errors=True)
