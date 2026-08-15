# -*- coding: utf-8 -*-
"""
SQLite 任务库
- 每次操作新建连接（函数级 get_conn()），context manager 提交
- WAL 模式 + busy_timeout，支持多线程并发读写
- task_id 格式 "j_" + uuid4().hex[:8]
"""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "app.db")

_ACTIVE_DB = DB_PATH  # init_db 指定的库路径，其余函数跟随使用

TIME_FMT = "%Y-%m-%d %H:%M:%S"
TZ_CN = timezone(timedelta(hours=8))

TASKS_DDL = """
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'pending',   -- pending/running/done/error
  progress REAL DEFAULT 0,
  status_text TEXT DEFAULT '',
  params_json TEXT NOT NULL DEFAULT '{}',   -- {order_files:[ids], configs:{type:version}, cookie, thread_count, enable_tax, exclude_ids}
  result_files_json TEXT DEFAULT '[]',      -- 输出文件名列表（相对 outputs/<id>/）
  log_json TEXT DEFAULT '[]',
  created_at TEXT, finished_at TEXT,
  error TEXT DEFAULT ''
);
"""


def _now():
    return datetime.now(TZ_CN).strftime(TIME_FMT)


def get_conn(db_path=None):
    """新建 SQLite 连接（WAL + busy_timeout）"""
    if db_path is None:
        db_path = _ACTIVE_DB
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(db_path=DB_PATH) -> None:
    """建表 + WAL + busy_timeout"""
    global _ACTIVE_DB
    _ACTIVE_DB = db_path
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = get_conn(db_path)
    try:
        with conn:
            conn.execute(TASKS_DDL)
    finally:
        conn.close()


def create_task(params: dict) -> str:
    """创建任务，返回 task_id（uuid hex 前8位，如 "j_3f8a2b1c"）"""
    task_id = "j_" + uuid.uuid4().hex[:8]
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                "INSERT INTO tasks (id, status, params_json, created_at) VALUES (?, 'pending', ?, ?)",
                (task_id, json.dumps(params, ensure_ascii=False), _now()),
            )
    finally:
        conn.close()
    return task_id


def update_task(task_id, **fields) -> None:
    """更新任务字段（status/progress/status_text/error/finished_at/result_files_json 等）"""
    if not fields:
        return
    conn = get_conn()
    try:
        with conn:
            if "finished_at" in fields and fields["finished_at"] is None:
                fields = dict(fields)
                fields["finished_at"] = _now()
            sets = ", ".join(f"{k}=?" for k in fields)
            conn.execute(f"UPDATE tasks SET {sets} WHERE id=?", (*fields.values(), task_id))
    finally:
        conn.close()


def get_task(task_id) -> dict | None:
    """按 id 取任务全字段 dict"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, status, progress, status_text, params_json, result_files_json, log_json, created_at, finished_at, error "
            "FROM tasks WHERE id=?",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "id": row[0],
        "status": row[1],
        "progress": row[2],
        "status_text": row[3],
        "params_json": json.loads(row[4] or "{}"),
        "result_files_json": json.loads(row[5] or "[]"),
        "log_json": json.loads(row[6] or "[]"),
        "created_at": row[7],
        "finished_at": row[8],
        "error": row[9],
    }


def list_tasks(status=None, limit=50) -> list[dict]:
    """任务列表，created_at DESC"""
    conn = get_conn()
    try:
        if status:
            rows = conn.execute(
                "SELECT id, status, progress, status_text, params_json, result_files_json, log_json, created_at, finished_at, error "
                "FROM tasks WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, status, progress, status_text, params_json, result_files_json, log_json, created_at, finished_at, error "
                "FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        conn.close()
    cols = ["id", "status", "progress", "status_text", "params_json", "result_files_json",
            "log_json", "created_at", "finished_at", "error"]
    return [dict(zip(cols, r)) for r in rows]


def delete_task(task_id) -> None:
    conn = get_conn()
    try:
        with conn:
            conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    finally:
        conn.close()


def mark_interrupted_tasks() -> None:
    """启动时: running/pending → error("进程中断")"""
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                "UPDATE tasks SET status='error', error='进程中断', finished_at=? WHERE status IN ('running','pending')",
                (_now(),),
            )
    finally:
        conn.close()


def append_log(task_id, entry: dict) -> None:
    """log_json 数组 append {ts,level,msg}（先读后写，单 UPDATE 原子完成）"""
    if "ts" not in entry:
        entry = dict(entry)
        entry["ts"] = _now()
    conn = get_conn()
    try:
        with conn:
            row = conn.execute("SELECT log_json FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                return
            logs = json.loads(row[0] or "[]")
            logs.append(entry)
            conn.execute(
                "UPDATE tasks SET log_json=? WHERE id=?",
                (json.dumps(logs, ensure_ascii=False), task_id),
            )
    finally:
        conn.close()


def get_logs(task_id, since=0) -> list:
    """log_json[since:] 切片"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT log_json FROM tasks WHERE id=?", (task_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return []
    logs = json.loads(row[0] or "[]")
    return logs[since:]
