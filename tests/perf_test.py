# -*- coding: utf-8 -*-
"""ProfitEngine 性能测试（独立脚本，非 pytest）

场景：
  1. 生成大订单 CSV（1000/3000 行：15 位订单号、70% 已收货 / 20% 已发货，待收货 / 10% 其他、
     50 个 SKU 随机、金额随机，按店铺拆 3 个文件）
  2. 复用 fixtures_gen 生成配置 fixture（成本表 50 SKU、链接表 3 店铺、推广/官补/排序表）
  3. monkeypatch engine.get_charge_order_list 返回固定 5.5 元，避免真实网络

阶段拆分（不改 engine.py）：
  - 配置加载/文件读取：monkeypatch 包装 engine.ProfitEngine.load_*/read_source_file 累计计时
  - 阶段2（并发查询）：整体耗时(enable_tax=True) - 整体耗时(enable_tax=False)
  - 阶段3（Excel 生成）：enable_tax=False 整体耗时 - 配置加载 - 文件读取（估算，含少量任务构建开销）

用法：
  python tests/perf_test.py [--rows 1000] [--rows2 3000] [--threads 4] [--repeat 1]
"""
import argparse
import os
import random
import shutil
import sys
import tempfile
import threading
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (PROJECT_ROOT,
          os.path.join(PROJECT_ROOT, "profit_service"),
          os.path.join(PROJECT_ROOT, "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

import engine  # noqa: E402
from fixtures_gen import (make_cost_xlsx, make_link_xlsx, make_order_csv,  # noqa: E402
                          make_promo_xlsx, make_sort_xlsx, make_subsidy_xlsx)

COOKIE = "perf-test-cookie"
STORES = [("庆余", range(1001, 1011)), ("趣味猴", range(2001, 2011)), ("大咖猴", range(3001, 3011))]
SKUS = ["SKU-%03d" % i for i in range(1, 51)]
DATE_STR = "2026年08月15日"
FILE_DATE = "20260815"


# ---------- 内存采样 ----------
class MemSampler:
    """后台线程采样进程 RSS，psutil 优先，ctypes(win32) 兜底；两者皆无则跳过"""

    def __init__(self):
        self.peak_mb = None
        self._stop = threading.Event()
        self._thread = None
        self._proc = None
        self._ctypes_fn = None
        try:
            import psutil
            self._proc = psutil.Process()
        except ImportError:
            try:
                import ctypes
                from ctypes import wintypes

                class _PMC(ctypes.Structure):
                    _fields_ = [
                        ("cb", wintypes.DWORD),
                        ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t),
                    ]

                psapi = ctypes.windll.psapi
                psapi.GetProcessMemoryInfo.argtypes = [
                    wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
                kernel32 = ctypes.windll.kernel32
                kernel32.GetCurrentProcess.restype = wintypes.HANDLE

                def _rss():
                    pmc = _PMC()
                    pmc.cb = ctypes.sizeof(_PMC)
                    if psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(),
                                                  ctypes.byref(pmc), pmc.cb):
                        return pmc.WorkingSetSize
                    return 0

                self._ctypes_fn = _rss
            except Exception:
                pass

    @property
    def available(self):
        return self._proc is not None or self._ctypes_fn is not None

    def _rss(self):
        if self._proc is not None:
            return self._proc.memory_info().rss
        return self._ctypes_fn()

    def start(self):
        if not self.available:
            return
        self._stop.clear()
        self.peak_mb = 0.0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                rss = self._rss()
                if rss > self.peak_mb * 1024 * 1024:
                    self.peak_mb = rss / 1024.0 / 1024.0
            except Exception:
                break
            self._stop.wait(0.05)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)


# ---------- 数据生成 ----------
def gen_order_rows(rng, n):
    """生成 n 行订单：70% 已收货 / 20% 已发货，待收货 / 10% 其他"""
    status_pool = (["已收货"] * 70 + ["已发货，待收货"] * 20 +
                   ["已取消", "待付款", "申请退款", "已关闭", "拼团失败"])
    seen = set()
    rows = []
    while len(rows) < n:
        order_no = str(rng.randint(10 ** 14, 10 ** 15 - 1))
        if order_no in seen:
            continue
        seen.add(order_no)
        status = rng.choice(status_pool)
        receive = round(rng.uniform(30, 3000), 2)
        rows.append([
            order_no,
            status,
            "",  # 商品id 由调用方按店铺填充
            rng.choice(SKUS),
            rng.randint(1, 5),
            receive,
            round(receive * rng.uniform(0, 0.05), 2),
            "2026-08-15 %02d:%02d:%02d" % (rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59)),
        ])
    return rows


def gen_fixtures(fixture_dir, n_rows, seed=42):
    """生成配置 fixture + 订单 CSV（3 店铺拆分），返回订单文件列表"""
    rng = random.Random(seed)

    cost_rows = []
    for i in range(1, 51):
        c = round(rng.uniform(10, 500), 2)
        cost_rows.append(["SKU-%03d" % i, "", "商品%d" % i, 1, c, c])
    make_cost_xlsx(os.path.join(fixture_dir, "成本表.xlsx"), rows=cost_rows)

    link_rows, prod_names = [], []
    for store, pids in STORES:
        for pid in pids:
            name = "%s产品%d" % (store, pid % 1000)
            prod_names.append(name)
            link_rows.append([store, name, str(pid)])
    make_link_xlsx(os.path.join(fixture_dir, "产品链接汇总表.xlsx"), rows=link_rows)

    for store, pids in STORES:
        make_promo_xlsx(
            os.path.join(fixture_dir, "推广报表_%s_%s.xlsx" % (store, FILE_DATE)),
            rows=[[str(pid), round(rng.uniform(0, 50), 2)] for pid in pids])

    make_subsidy_xlsx(os.path.join(fixture_dir, "官补映射表.xlsx"),
                      rows=[["1001", "SKU-001", 10]])
    make_sort_xlsx(os.path.join(fixture_dir, "产品汇总表.xlsx"), values=prod_names)

    per_store = n_rows // len(STORES)
    files = []
    for i, (store, pids) in enumerate(STORES):
        n = per_store + (1 if i < n_rows % len(STORES) else 0)
        rows = gen_order_rows(rng, n)
        for r in rows:
            r[2] = str(rng.choice(list(pids)))
        path = os.path.join(fixture_dir, "%s订单_%s.csv" % (store, FILE_DATE))
        make_order_csv(path, rows)
        files.append(path)
    return files


# ---------- Mock API ----------
def fake_charge_order_list(order_no, cookie):
    """固定返回 5.5 元（基础服务费 5.5 + 进口关税 0），fee_ok=True"""
    return {"success": True, "data": [
        {"quotedAmount": 5.5, "feeName": "基础服务费"},
        {"quotedAmount": 0.0, "feeName": "进口关税"},
    ]}


# ---------- 计时包装 ----------
def time_wrapped(original, counter):
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            counter["total"] += time.perf_counter() - t0
    return wrapper


def run_scenario(files, configs, threads, enable_tax, label):
    """执行一次 process()，返回 {label, total, phases{...}, result, peak_mb}"""
    global RUN_COUNTER
    RUN_COUNTER += 1
    out_dir = os.path.join(OUTPUT_DIR, "run_%03d" % RUN_COUNTER)
    os.makedirs(out_dir, exist_ok=True)

    eng = engine.ProfitEngine(log_cb=lambda m: None, progress_cb=lambda p, t: None)

    counters = {}
    saved = {}
    for attr in ("load_cost_map", "load_link_map", "load_promo_map",
                 "load_subsidy_map", "load_sort_list", "read_source_file"):
        orig = getattr(engine.ProfitEngine, attr)
        saved[attr] = orig
        counters[attr] = {"total": 0.0}
        setattr(engine.ProfitEngine, attr, time_wrapped(orig, counters[attr]))

    original_get = engine.get_charge_order_list
    engine.get_charge_order_list = fake_charge_order_list
    sampler = MemSampler()
    sampler.start()
    t0 = time.perf_counter()
    try:
        result = eng.process(
            order_files=files, configs=configs, cookie=COOKIE,
            thread_count=threads, enable_tax=enable_tax,
            exclude_ids="", output_dir=out_dir)
    finally:
        elapsed = time.perf_counter() - t0
        sampler.stop()
        engine.get_charge_order_list = original_get
        for attr, orig in saved.items():
            setattr(engine.ProfitEngine, attr, orig)

    cfg_load = sum(c["total"] for k, c in counters.items() if k.startswith("load_"))
    return {
        "label": label,
        "total": elapsed,
        "cfg_load": cfg_load,
        "read_source": counters["read_source_file"]["total"],
        "result": result,
        "peak_mb": sampler.peak_mb,
    }


# ---------- 主流程 ----------
def main():
    ap = argparse.ArgumentParser(description="ProfitEngine 性能测试")
    ap.add_argument("--rows", type=int, default=1000, help="场景一订单行数")
    ap.add_argument("--rows2", type=int, default=3000, help="场景二订单行数(趋势)")
    ap.add_argument("--threads", type=int, default=4, help="税运查询并发线程数")
    ap.add_argument("--repeat", type=int, default=1, help="每场景重复次数(取平均)")
    ap.add_argument("--keep", action="store_true", help="保留临时目录")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    global OUTPUT_DIR, RUN_COUNTER
    RUN_COUNTER = 0
    tmp_root = tempfile.mkdtemp(prefix="perf_engine_")
    OUTPUT_DIR = os.path.join(tmp_root, "outputs")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 78)
    print("ProfitEngine 性能测试  |  %s  |  Python %s" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                                                          sys.version.split()[0]))
    print("rows=%s, rows2=%s, threads=%s, repeat=%s  |  API: mock(固定5.5元)"
          % (args.rows, args.rows2, args.threads, args.repeat))
    print("=" * 78)

    try:
        fixture_dir = os.path.join(tmp_root, "fixtures")
        os.makedirs(fixture_dir, exist_ok=True)

        configs = {
            "cost": os.path.join(fixture_dir, "成本表.xlsx"),
            "link": os.path.join(fixture_dir, "产品链接汇总表.xlsx"),
            "promo": [os.path.join(fixture_dir, "推广报表_%s_%s.xlsx" % (s, FILE_DATE)) for s, _ in STORES],
            "subsidy": os.path.join(fixture_dir, "官补映射表.xlsx"),
            "sort": os.path.join(fixture_dir, "产品汇总表.xlsx"),
        }

        results = {}
        for n_rows, tag in ((args.rows, "A"), (args.rows2, "B")):
            files = gen_fixtures(fixture_dir, n_rows, seed=1000 + n_rows)
            label = "%s: %d 行" % (tag, n_rows)
            sums = {"tax": 0.0, "notax": 0.0, "cfg_load": 0.0, "read_source": 0.0, "peak_mb": 0.0}
            last = {}
            for rep in range(args.repeat):
                for enable_tax in (True, False):
                    scen = run_scenario(files, configs, args.threads, enable_tax,
                                        "%s tax=%s" % (label, enable_tax))
                    key = "tax" if enable_tax else "notax"
                    sums[key] += scen["total"]
                    sums["cfg_load"] += scen["cfg_load"]
                    sums["read_source"] += scen["read_source"]
                    if scen["peak_mb"] is not None:
                        sums["peak_mb"] += scen["peak_mb"]
                    last[key] = scen
            n_run = args.repeat
            results[tag] = {
                "label": label,
                "rows": n_rows,
                "files": files,
                "total_tax": sums["tax"] / n_run,
                "total_notax": sums["notax"] / n_run,
                "avg_cfg_load": sums["cfg_load"] / (n_run * 2),
                "avg_read": sums["read_source"] / (n_run * 2),
                "avg_peak_mb": (sums["peak_mb"] / (n_run * 2)) if sums["peak_mb"] else None,
                "stats": last["notax"]["result"]["stats"],
                "out_files": last["notax"]["result"]["files"],
            }

        # 极小规模基准（估算配置加载 + 固定开销）
        mini_dir = os.path.join(fixture_dir, "mini")
        os.makedirs(mini_dir, exist_ok=True)
        mini_files = []
        for s, (store, pids) in enumerate(STORES):
            p = os.path.join(mini_dir, "%s订单_%s.csv" % (store, FILE_DATE))
            rows = []
            for j in range(2):
                order_no = str(100000000000000 + s * 1000 + j)
                rows.append([order_no, "已收货", str(min(pids)), SKUS[0], 1, 100.0, 1.0,
                             "2026-08-15 08:00:00"])
            make_order_csv(p, rows)
            mini_files.append(p)
        t_min = 0.0
        for rep in range(args.repeat):
            t_min += run_scenario(mini_files, configs, args.threads, False, "")["total"]
        t_min /= args.repeat

        # ---------- 汇总报表 ----------
        print()
        print("%-16s %10s %10s %10s %10s %10s %8s %10s" %
              ("场景", "总耗时(s)", "税运查询(s)", "Excel生成(s)", "配置加载(s)", "读文件(s)", "峰值MB", "文件大小"))
        print("-" * 78)
        rows_out = []
        for tag in ("A", "B"):
            r = results[tag]
            phase2 = r["total_tax"] - r["total_notax"]
            phase3 = r["total_notax"] - r["avg_cfg_load"] - r["avg_read"]
            out_size = sum(os.path.getsize(f) for f in r["out_files"])
            ok = "OK" if phase3 < 10 else "超时"
            print("%-16s %10.2f %10.2f %10.2f %10.2f %10.2f %8s %8.1f KB  [Excel %s]" %
                  (r["label"], r["total_tax"], phase2, phase3,
                   r["avg_cfg_load"], r["avg_read"],
                   ("%.0f" % r["avg_peak_mb"]) if r["avg_peak_mb"] else "-",
                   out_size / 1024.0, ok))
            print("    %-14s 有效订单=%d/%d 原始行  |  输出: %s" %
                  (" ", r["stats"]["total_tasks"], r["rows"], os.path.basename(r["out_files"][0])))
            rows_out.append({
                "label": r["label"], "total_tax": r["total_tax"], "phase2": phase2,
                "phase3": phase3, "cfg": r["avg_cfg_load"], "read": r["avg_read"],
                "peak": r["avg_peak_mb"], "size_kb": out_size / 1024.0,
                "tasks": r["stats"]["total_tasks"], "ok": ok,
            })

        print("-" * 78)
        print("极小基准(配置加载+小文件固定开销): %.2fs  |  目标: Excel 生成 < 10s" % t_min)
        print("内存采样: %s" % ("psutil" if _has_psutil() else ("ctypes(win32)" if _has_ctypes() else "不可用，已跳过")))
    finally:
        if not args.keep:
            shutil.rmtree(tmp_root, ignore_errors=True)


def _has_psutil():
    try:
        import psutil
        return True
    except ImportError:
        return False


def _has_ctypes():
    try:
        import ctypes
        return hasattr(ctypes, "windll")
    except Exception:
        return False


if __name__ == "__main__":
    main()
