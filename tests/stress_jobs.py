# -*- coding: utf-8 -*-
"""task_manager 压力测试（独立脚本，非 pytest）

验证目标（MAX_CONCURRENT=2 / 排队上限 MAX_QUEUED=10）:
  S1  排队上限: 连续提交 12 → 10 接受 / 第 11-12 个返回 "服务忙"; 任意时刻 running ≤ 2; 终态 10 done
  S1b 控制组观察（不断言）: 无状态写延迟时连续提交 12 → 观察实际接受数
  S2  混合场景: 删除 running 任务 → (False, "任务运行中，无法删除")
  S3  多线程提交: 10 线程同时 submit 各 1 → 全部接受、无异常、任务数正确

注意:
  - 排队判定只统计 DB pending 行，worker 取任务(pending→running)是异步的，存在竞态窗口；
    S1 用 150ms 状态写延迟（模拟高负载下 SQLite 争用）确定性复现该窗口，否则 12 个会全部接受。
  - configs.resolve_configs 必须返回 dict（返回 (fake, None) 元组会被 submit_job 判为配置缺失拒绝）。

用法:
  venv/Scripts/python.exe tests/stress_jobs.py
"""
import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "profit_service"))

import configs
import db
import files_store
import logging_setup
import security
import stats
import task_manager
import tax_cache

TMP = tempfile.mkdtemp(prefix="stress_jobs_")
print(f"[env] 临时目录: {TMP}")

# ---------- 环境隔离（db/日志/缓存/统计全部指向临时目录） ----------
db.DB_PATH = os.path.join(TMP, "app.db")
db._ACTIVE_DB = db.DB_PATH
db.init_db(db.DB_PATH)

logging_setup.BASE_DIR = TMP
security.TOKEN_FILE = os.path.join(TMP, "token.txt")

task_manager.TASKS_DIR = os.path.join(TMP, "tasks")
task_manager.OUTPUTS_DIR = os.path.join(TMP, "outputs")
files_store.UPLOADS_DIR = os.path.join(TMP, "uploads")

tax_cache.load_cache(os.path.join(TMP, "tax_cache.json"))
stats.load_stats(os.path.join(TMP, "stats.json"))

# ---------- 假配置 / 假快照 / 慢引擎 ----------
FAKE_CONFIGS = {
    "cost": "C:/fake/cost.xlsx",
    "link": "C:/fake/link.xlsx",
    "promo": ["C:/fake/promo1.xlsx"],
    "subsidy": None,
    "sort": None,
}
configs.resolve_configs = lambda versions=None, base_dir=None: dict(FAKE_CONFIGS)
files_store.find_order_file = lambda fid: {"id": fid, "name": f"{fid}.csv", "path": os.path.join(TMP, "uploads", f"{fid}.csv")}
files_store.snapshot_inputs = lambda *a, **k: {"order_files": ["C:/fake/order.csv"], "configs": dict(FAKE_CONFIGS)}

engine_calls = {"n": 0}


class SlowProfitEngine:
    """慢假引擎: process 睡 1s 模拟真实耗时，返回空 files + 一个税运缓存项"""

    def __init__(self, log_cb=None, progress_cb=None):
        self._log_cb = log_cb or (lambda msg: None)
        self._progress_cb = progress_cb or (lambda pct, text: None)

    def process(self, order_files, configs, cookie, thread_count=2, enable_tax=True,
                exclude_ids="", output_dir=None):
        engine_calls["n"] += 1
        self._progress_cb(10, "模拟处理中...")
        time.sleep(1.0)
        self._progress_cb(100, "模拟完成")
        return {"files": [], "stats": {},
                "tax_cache": {"SKU-STRESS-1": {"amount": 1.5, "fee_details": [], "fee_ok": True, "msg": ""}}}


task_manager.ProfitEngine = SlowProfitEngine

# ---------- 排队判定窗口模拟（仅 S1 开启） ----------
_RUNNING_LATENCY = {"sec": 0.0}
_orig_update_task = db.update_task


def slow_update_task(task_id, **fields):
    if fields.get("status") == "running" and _RUNNING_LATENCY["sec"]:
        time.sleep(_RUNNING_LATENCY["sec"])
    return _orig_update_task(task_id, **fields)


db.update_task = slow_update_task

# ---------- force_flush 调用计数 ----------
flush_calls = []
_orig_force_flush = tax_cache.force_flush


def counting_force_flush():
    flush_calls.append(time.time())
    return _orig_force_flush()


tax_cache.force_flush = counting_force_flush

task_manager.init_task_manager()

# ---------- 工具函数 ----------
results = []
observations = []


def record(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


def make_params(seed):
    return {
        "cookie": f"stress_cookie_{seed}",
        "order_files": [f"f_stress_{seed}"],
        "configs": {},
        "thread_count": 2,
        "enable_tax": True,
        "exclude_ids": "",
    }


def counts():
    rows = db.list_tasks()
    return {s: sum(1 for r in rows if r["status"] == s) for s in ("pending", "running", "done", "error")}


def wait_quiescent(timeout=60, interval=0.05):
    """等待无 pending/running（全部收敛到 done/error）"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        c = counts()
        if c["pending"] == 0 and c["running"] == 0:
            return c
        time.sleep(interval)
    raise RuntimeError(f"等待任务收敛超时: {counts()}")


def wait_status(task_id, status, timeout=10, interval=0.02):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        t = db.get_task(task_id)
        last = t
        if t and t["status"] == status:
            return t
        time.sleep(interval)
    raise RuntimeError(f"任务 {task_id} 等待状态 {status} 超时: 当前 {last and last['status']}")


# ---------- S1: 排队上限 ----------
def scenario1():
    print("\n=== S1 排队上限: 连续提交 12 个任务（DB 状态写延迟 150ms 模拟高负载）===")
    _RUNNING_LATENCY["sec"] = 0.15
    samples = []
    stop = threading.Event()
    t0 = time.time()

    def sample():
        while not stop.is_set():
            c = counts()
            samples.append((time.time() - t0, c["running"], c["pending"], c["done"], c["error"]))
            time.sleep(0.02)

    th = threading.Thread(target=sample, daemon=True)
    th.start()

    accepted, rejected = [], []
    try:
        for i in range(12):
            tid, err = task_manager.submit_job(make_params(f"s1_{i}"))
            (accepted if tid else rejected).append((i, tid, err))
        observations.append(f"S1 提交期: 接受 {len(accepted)} / 拒绝 {len(rejected)}")
        c = wait_quiescent()
    finally:
        stop.set()
        th.join()
    _RUNNING_LATENCY["sec"] = 0.0

    rejected_idx = [i for i, _, _ in rejected]
    rejected_msgs = [err for _, _, err in rejected]
    max_running = max((s[1] for s in samples), default=0)
    max_pending = max((s[2] for s in samples), default=0)

    record("S1-1 提交 12 个: 10 接受 / 2 拒绝", len(accepted) == 10 and rejected_idx == [10, 11],
           f"接受 {len(accepted)} 个, 拒绝序号 {rejected_idx}")
    record("S1-2 拒绝文案为 服务忙", all(m and m.startswith("服务忙") for m in rejected_msgs),
           f"{rejected_msgs}")
    record("S1-3 任意时刻 running <= 2", max_running <= 2, f"峰值 running={max_running}")
    record("S1-4 任意时刻 pending <= 10", max_pending <= 10, f"峰值 pending={max_pending}")
    record("S1-5 终态: 10 done / 0 error", c["done"] == 10 and c["error"] == 0 and c["pending"] == 0 and c["running"] == 0,
           f"{c}")
    record("S1-6 被拒任务未入库", all(db.get_task(tid) is None for _, tid, _ in rejected), "")
    record("S1-7 引擎实际只跑 10 个", engine_calls["n"] == 10, f"engine.process 调用 {engine_calls['n']} 次")

    flush_ok = len(flush_calls) >= 10 and os.path.isfile(os.path.join(TMP, "tax_cache.json"))
    try:
        with open(os.path.join(TMP, "tax_cache.json"), encoding="utf-8") as f:
            json.load(f)
    except Exception as e:
        flush_ok = False
        record("S1-8 tax_cache.force_flush 并发无异常", False, f"缓存文件损坏: {e}")
    else:
        record("S1-8 tax_cache.force_flush 并发无异常", flush_ok,
               f"force_flush 调用 {len(flush_calls)} 次, 缓存文件存在且可解析")

    timeline = []
    prev = None
    for s in samples:
        if prev is None or s[1:] != prev[1:]:
            timeline.append(s)
            prev = s
    if timeline and timeline[-1] != samples[-1]:
        timeline.append(samples[-1])
    print(f"\n[S1 时序观察] 共 {len(samples)} 个采样点, 状态变化 {len(timeline)} 行 (t/running/pending/done/error):")
    for t, r, p, d, e in timeline:
        print(f"  t={t:6.2f}  running={r}  pending={p}  done={d}  error={e}")

# ---------- S2: 删除 running 任务 ----------
def scenario2():
    print("\n=== S2 混合场景: 任务运行中删除应被拒绝 ===")
    tid, err = task_manager.submit_job(make_params("s2_0"))
    if not tid:
        record("S2-1 提交成功", False, str(err))
        return
    wait_status(tid, "running")
    ok, msg = task_manager.delete_job(tid)
    record("S2-1 删除 running 任务被拒 (False)", ok is False and "运行中" in msg, f"返回 ({ok}, {msg!r})")
    ok2, msg2 = task_manager.delete_job("j_deadbeef")
    record("S2-2 删除不存在任务被拒", ok2 is False and msg2 == "任务不存在", f"返回 ({ok2}, {msg2!r})")
    wait_quiescent()
    ok3, msg3 = task_manager.delete_job(tid)
    record("S2-3 done 后删除成功", ok3 is True and db.get_task(tid) is None, f"返回 ({ok3}, {msg3!r})")


# ---------- S3: 多线程提交 ----------
def scenario3():
    print("\n=== S3 多线程提交: 10 线程同时 submit 各 1 个 ===")
    n_before = len(db.list_tasks())
    barrier = threading.Barrier(10)
    out = {}
    errors = {}

    def worker(i):
        try:
            barrier.wait()
            tid, err = task_manager.submit_job(make_params(f"s3_{i}"))
            out[i] = (tid, err)
        except Exception as e:
            errors[i] = repr(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    accepted = [tid for tid, err in out.values() if tid and not err]
    record("S3-1 10 线程全部接受且无异常", len(out) == 10 and len(errors) == 0 and len(accepted) == 10,
           f"接受 {len(accepted)}/10, 线程异常 {errors}")
    c = wait_quiescent()
    delta = len(db.list_tasks()) - n_before
    all_done = all(db.get_task(tid)["status"] == "done" for tid in accepted)
    record("S3-2 任务数正确且全部 done", delta == 10 and all_done and len(accepted) == 10,
           f"入库增量 {delta}, 新任务 10/10 done, 全局终态 {c}")


# ---------- S1b: 控制组观察（不断言） ----------
def scenario1b():
    print("\n=== S1b 控制组观察: 无状态写延迟时连续提交 12 个 ===")
    before = engine_calls["n"]
    accepted, rejected = [], []
    for i in range(12):
        tid, err = task_manager.submit_job(make_params(f"s1b_{i}"))
        (accepted if tid else rejected).append((i, tid, err))
    c = wait_quiescent()
    all_done = all(db.get_task(tid)["status"] == "done" for _, tid, _ in accepted)
    observations.append(f"S1b 控制组: 接受 {len(accepted)} / 拒绝 {len(rejected)}"
                        f" (拒绝序号 {[i for i, _, _ in rejected]}, 引擎调用 +{engine_calls['n'] - before})")
    record("S1b 控制组完成且全部 done", all_done and engine_calls["n"] - before == len(accepted),
           f"接受 {len(accepted)} 全部 done, 终态 {c}")


# ---------- 汇总 ----------
def main():
    scenario1()
    scenario2()
    scenario3()
    scenario1b()

    print("\n========== 压测汇总 ==========")
    for name, ok, detail in results:
        print(f"  [{('PASS' if ok else 'FAIL'):4}] {name}" + (f"  -- {detail}" if detail else ""))
    print("\n[观察数据]")
    for o in observations:
        print(f"  {o}")
    n_pass = sum(1 for _, ok, _ in results if ok)
    n_fail = len(results) - n_pass
    print(f"\n结果: {n_pass} PASS / {n_fail} FAIL (共 {len(results)} 项)")
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()

