# -*- coding: utf-8 -*-
"""稳定性验证：中断恢复 / tax_cache 恢复 / 输出清理 / 孤儿清理 / db 并发写

独立脚本，直接运行: venv\\Scripts\\python.exe tests\\stability_test.py
也可被 pytest 收集（test_* 函数 + tmp_path fixture，check 失败即抛 AssertionError）。
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVC = os.path.join(ROOT, "profit_service")
if SVC not in sys.path:
    sys.path.insert(0, SVC)

import db
import files_store
import task_manager
import tax_cache

PASS, FAIL = "PASS", "FAIL"
_results = []


def check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    if not cond and os.environ.get("PYTEST_CURRENT_TEST"):
        raise AssertionError(f"{name} {detail}")
    return bool(cond)


def test_interrupted_recovery(tmp_path):
    """中断恢复: running/pending -> error("进程中断")，done 不受影响"""
    tmp = str(tmp_path)
    db_path = os.path.join(tmp, "interrupt", "app.db")
    db.init_db(db_path)
    t_run = db.create_task({"cookie": "c"})
    t_pend = db.create_task({"cookie": "c"})
    t_done = db.create_task({"cookie": "c"})
    db.update_task(t_run, status="running", progress=50)
    db.update_task(t_done, status="done", progress=100)
    db.mark_interrupted_tasks()
    r1 = db.get_task(t_run)
    r2 = db.get_task(t_pend)
    r3 = db.get_task(t_done)
    ok1 = check("中断恢复: running -> error", r1["status"] == "error" and "进程中断" in r1["error"], f"got {r1['status']}/{r1['error']}")
    ok2 = check("中断恢复: pending -> error", r2["status"] == "error" and "进程中断" in r2["error"], f"got {r2['status']}/{r2['error']}")
    check("中断恢复: done 不受影响", r3["status"] == "done", f"got {r3['status']}")


def test_tax_cache_roundtrip(tmp_path):
    """tax_cache: put->force_flush->重新 load->get 命中；损坏 JSON 不抛异常"""
    tmp = str(tmp_path)
    cache_path = os.path.join(tmp, "tax", "tax_cache.json")
    tax_cache._cache = {}
    tax_cache._dirty = 0
    tax_cache.load_cache(cache_path)
    for i in range(5):
        tax_cache.put(f"key{i}", {"amount": i * 100.0, "fee_details": [], "fee_ok": True, "msg": "ok"})
    tax_cache.force_flush()
    assert os.path.isfile(cache_path), "force_flush 未写盘"
    tax_cache._cache = {}
    tax_cache.load_cache(cache_path)
    hit = all(tax_cache.get(f"key{i}") and tax_cache.get(f"key{i}")["amount"] == i * 100.0 for i in range(5))
    check("tax_cache: 落盘重载命中", hit)
    corrupt = os.path.join(tmp, "tax", "corrupt.json")
    with open(corrupt, "wb") as f:
        f.write(b"\x00\xff\xfe{not json!!!")
    try:
        tax_cache.load_cache(corrupt)
        no_raise = True
    except Exception as e:
        no_raise = False
        detail = f"抛异常: {e}"
    else:
        detail = ""
    check("tax_cache: 损坏 JSON 不抛异常", no_raise, detail)
    tax_cache.load_cache(cache_path)  # 恢复指向正常路径


def test_cleanup_outputs(tmp_path):
    """cleanup_outputs(24h): 旧目录删除、新目录保留"""
    out_dir = os.path.join(str(tmp_path), "outputs")
    os.makedirs(out_dir, exist_ok=True)
    old = os.path.join(out_dir, "j_old0001")
    new = os.path.join(out_dir, "j_new0002")
    os.makedirs(old)
    os.makedirs(new)
    with open(os.path.join(old, "a.xlsx"), "w") as f:
        f.write("x")
    with open(os.path.join(new, "b.xlsx"), "w") as f:
        f.write("x")
    past = time.time() - 25 * 3600
    os.utime(old, (past, past))
    old_mtime = os.path.getmtime(old)
    new_mtime = os.path.getmtime(new)
    assert old_mtime < time.time() - 24 * 3600, "测试构造失败: 旧目录 mtime 未超过 24h"
    assert new_mtime >= time.time() - 24 * 3600, "测试构造失败: 新目录 mtime 异常"
    orig = task_manager.OUTPUTS_DIR
    task_manager.OUTPUTS_DIR = out_dir
    try:
        task_manager.cleanup_outputs(24)
        ok_del = not os.path.exists(old)
        ok_keep = os.path.exists(new)
    finally:
        task_manager.OUTPUTS_DIR = orig
    check("cleanup_outputs: 超龄(25h)目录删除", ok_del)
    check("cleanup_outputs: 新目录保留", ok_keep)


def test_cleanup_orphans(tmp_path):
    """cleanup_orphans: .part 残留必删、超龄上传删、新文件保留"""
    up_dir = os.path.join(str(tmp_path), "uploads")
    os.makedirs(up_dir, exist_ok=True)
    old = os.path.join(up_dir, "old_20240101.xlsx")
    new = os.path.join(up_dir, "new_20260815.xlsx")
    part = os.path.join(up_dir, "resume.xlsx.part")
    for p in (old, new, part):
        with open(p, "wb") as f:
            f.write(b"data")
    past = time.time() - 8 * 86400
    os.utime(old, (past, past))
    orig = files_store.UPLOADS_DIR
    files_store.UPLOADS_DIR = up_dir
    try:
        removed = files_store.cleanup_orphans(max_age_days=7)
        ok_old = not os.path.exists(old) and os.path.basename(old) in removed
        ok_part = not os.path.exists(part) and os.path.basename(part) in removed
        ok_new = os.path.exists(new) and os.path.basename(new) not in removed
    finally:
        files_store.UPLOADS_DIR = orig
    check("cleanup_orphans: 超龄(8天)上传删除", ok_old)
    check("cleanup_orphans: .part 残留删除", ok_part)
    check("cleanup_orphans: 新文件保留", ok_new)


def test_concurrent_append_log(tmp_path):
    """db 并发写: 10 线程 × 不同任务 × 100 条 append_log，无 SQLITE_BUSY"""
    db_path = os.path.join(str(tmp_path), "conc", "app.db")
    db.init_db(db_path)
    task_ids = [db.create_task({"cookie": "c"}) for _ in range(10)]
    errors = []
    barrier = threading.Barrier(10)

    def worker(tid):
        try:
            barrier.wait(timeout=30)
            for i in range(100):
                db.append_log(tid, {"level": "INFO", "msg": f"msg-{i}"})
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(tid,)) for tid in task_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    busy = [e for e in errors if isinstance(e, sqlite3.OperationalError) and "busy" in str(e).lower()]
    counts = [len(db.get_logs(tid)) for tid in task_ids]
    check("并发写: 无异常", not errors, f"异常 {len(errors)} 个: {errors[:3]}")
    check("并发写: 无 SQLITE_BUSY", not busy, f"busy {len(busy)} 个")
    check("并发写: 每任务 100 条完整", all(c == 100 for c in counts), f"条数分布: {counts}")


def main():
    tmp_root = tempfile.mkdtemp(prefix="stability_")
    try:
        test_interrupted_recovery(tmp_root)
        test_tax_cache_roundtrip(tmp_root)
        test_cleanup_outputs(tmp_root)
        test_cleanup_orphans(tmp_root)
        test_concurrent_append_log(tmp_root)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    print()
    print(f"{'用例':<34} {'结果':<6} 说明")
    print("-" * 70)
    for name, ok, detail in _results:
        print(f"{name:<34} {PASS if ok else FAIL:<6} {detail}")
    print("-" * 70)
    failed = [r for r in _results if not r[1]]
    print(f"总计 {len(_results)} 项: {len(_results) - len(failed)} PASS, {len(failed)} FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
