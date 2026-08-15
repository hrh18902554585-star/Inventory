# -*- coding: utf-8 -*-
"""load_* 配置加载方法单元测试（契约第 12 节 tests/test_engine_loaders.py）
- fixture 全部用 fixtures_gen 生成函数 + tmp_path，每个用例独立生成
- 只测 5 个 load_* 方法，不触发网络请求
"""
from datetime import date

import pytest

from engine import EngineError, ProfitEngine
from fixtures_gen import (
    make_cost_xlsx,
    make_link_xlsx,
    make_promo_xlsx,
    make_sort_xlsx,
    make_subsidy_xlsx,
)


@pytest.fixture
def engine():
    return ProfitEngine(log_cb=lambda msg: None)


# ---------- load_cost_map ----------

def test_load_cost_map_normal(engine, tmp_path):
    path = make_cost_xlsx(
        str(tmp_path / "成本表.xlsx"),
        rows=[
            ["SKU-A", "", "雅培金装", 1, 50, 50],
            ["SKU-B", "", "雅培金装", 1, 60, 60],
        ],
        baby_codes=["CODE-999", "CODE-888"],
    )
    cost_map, baby_codes = engine.load_cost_map(path)
    assert set(cost_map) == {"SKU-A", "SKU-B"}
    assert cost_map["SKU-A"] == [{"start": None, "end": None, "cost": 50.0}]
    assert cost_map["SKU-B"] == [{"start": None, "end": None, "cost": 60.0}]
    assert baby_codes == {"CODE-999", "CODE-888"}


def test_load_cost_map_without_baby_sheet(engine, tmp_path):
    path = make_cost_xlsx(
        str(tmp_path / "成本表.xlsx"),
        rows=[["SKU-A", "", "", 1, 50, 50]],
        baby_codes=None,
    )
    cost_map, baby_codes = engine.load_cost_map(path)
    assert cost_map["SKU-A"][0]["cost"] == 50.0
    assert baby_codes == set()


def test_load_cost_map_file_not_found(engine, tmp_path):
    with pytest.raises(EngineError) as exc:
        engine.load_cost_map(str(tmp_path / "不存在.xlsx"))
    assert exc.value.code == 20101


def test_load_cost_map_missing_headers(engine, tmp_path):
    path = make_cost_xlsx(
        str(tmp_path / "成本表.xlsx"),
        headers=["组合编码", "单品编码"],
        rows=[["SKU-A", ""]],
    )
    with pytest.raises(EngineError) as exc:
        engine.load_cost_map(path)
    assert exc.value.code == 20103


def test_load_cost_map_g_column_fallback(engine, tmp_path):
    # 无日期表头时兜底取 G 列（索引 6）作为日期区间
    path = make_cost_xlsx(
        str(tmp_path / "成本表.xlsx"),
        headers=["组合编码", "单品编码", "商品名称", "数量", "单品成本", "sku成本", "备注"],
        rows=[
            ["SKU-A", "", "雅培金装", 1, 50, 50, "2026/05/01-2026/05/31"],
            ["SKU-B", "", "雅培金装", 1, 60, 60, ""],
        ],
    )
    cost_map, _ = engine.load_cost_map(path)
    assert cost_map["SKU-A"][0]["start"] == date(2026, 5, 1)
    assert cost_map["SKU-A"][0]["end"] == date(2026, 5, 31)
    assert cost_map["SKU-B"][0]["start"] is None
    assert cost_map["SKU-B"][0]["end"] is None


def test_load_cost_map_date_range(engine, tmp_path):
    path = make_cost_xlsx(
        str(tmp_path / "成本表.xlsx"),
        headers=["组合编码", "单品编码", "商品名称", "数量", "单品成本", "sku成本", "日期"],
        rows=[
            ["SKU-A", "", "雅培金装", 1, 50, 50, "2026/05/01-2026/05/31"],
            ["SKU-A", "", "雅培金装", 1, 40, 40, "2025/01/01-至今"],
        ],
    )
    cost_map, _ = engine.load_cost_map(path)
    rules = cost_map["SKU-A"]
    assert len(rules) == 2
    r1, r2 = rules[0], rules[1]
    assert r1["start"] == date(2026, 5, 1) and r1["end"] == date(2026, 5, 31)
    assert r2["start"] == date(2025, 1, 1) and r2["end"] is None
    # 区间匹配：区间内日期命中 r1；无上界规则命中 r2
    assert r1["start"] <= date(2026, 5, 15) <= r1["end"]
    assert date(2026, 6, 1) >= r2["start"]


# ---------- load_link_map ----------

def test_load_link_map_normal(engine, tmp_path):
    path = make_link_xlsx(
        str(tmp_path / "产品链接汇总表.xlsx"),
        rows=[
            ["庆余", "雅培金装", "1001"],
            ["趣味猴", "摩可纳8号", "2001"],
            ["庆余", None, "3001"],
            ["庆余", "无ID商品", ""],
        ],
    )
    link_map = engine.load_link_map(path)
    assert link_map == {
        "庆余": {"1001": "雅培金装", "3001": "未知产品"},
        "趣味猴": {"2001": "摩可纳8号"},
    }


def test_load_link_map_id_strips_dot_zero(engine, tmp_path):
    path = make_link_xlsx(
        str(tmp_path / "产品链接汇总表.xlsx"),
        rows=[
            ["庆余", "雅培金装", "1001.0"],
            ["庆余", "摩可纳8号", 2002],
        ],
    )
    link_map = engine.load_link_map(path)
    assert "1001" in link_map["庆余"]
    assert "1001.0" not in link_map["庆余"]
    assert "2002" in link_map["庆余"]


def test_load_link_map_missing_headers(engine, tmp_path):
    path = make_link_xlsx(
        str(tmp_path / "产品链接汇总表.xlsx"),
        headers=["店铺名称", "产品名称"],
        rows=[["庆余", "雅培金装"]],
    )
    with pytest.raises(EngineError) as exc:
        engine.load_link_map(path)
    assert exc.value.code == 20113


# ---------- load_promo_map ----------

def test_load_promo_map_empty_raises(engine):
    with pytest.raises(EngineError) as exc:
        engine.load_promo_map([])
    assert exc.value.code == 20121


def test_load_promo_map_multi_file_merge(engine, tmp_path):
    logs = []
    engine = ProfitEngine(log_cb=logs.append)
    f1 = make_promo_xlsx(str(tmp_path / "推广报表_庆余.xlsx"), rows=[["1001", 20], ["1002", 5]])
    f2 = make_promo_xlsx(str(tmp_path / "推广报表_庆余_20260527.xlsx"), rows=[["1001", 30]])
    f3 = make_promo_xlsx(str(tmp_path / "推广报表_趣味猴.xlsx"), rows=[["2001", 10]])
    promo_map = engine.load_promo_map([f1, f2, f3, str(tmp_path / "不存在.xlsx")])
    assert set(promo_map) == {"庆余", "趣味猴"}
    assert promo_map["庆余"]["1001"]["total"] == 50.0
    assert promo_map["庆余"]["1002"]["total"] == 5.0
    assert promo_map["庆余"]["1001"]["daily"] == {"2026年05月27日": 30.0}
    assert promo_map["趣味猴"]["2001"]["total"] == 10.0


def test_load_promo_map_missing_headers_skipped(engine, tmp_path):
    logs = []
    engine = ProfitEngine(log_cb=logs.append)
    bad = make_promo_xlsx(
        str(tmp_path / "推广报表_庆余_坏.xlsx"),
        headers=["商品ID"],
        rows=[["1001"]],
    )
    good = make_promo_xlsx(str(tmp_path / "推广报表_庆余_好.xlsx"), rows=[["1001", 20]])
    promo_map = engine.load_promo_map([bad, good])
    assert promo_map == {"庆余": {"1001": {"total": 20.0, "daily": {}}}}
    assert any("已跳过" in m for m in logs)


def test_load_promo_map_date_column(engine, tmp_path):
    path = make_promo_xlsx(
        str(tmp_path / "推广报表_庆余.xlsx"),
        headers=["商品ID", "总花费(元)", "日期"],
        rows=[["1001", 12, "2026/05/26"], ["1002", 8, "2026年5月3日"]],
    )
    promo_map = engine.load_promo_map([path])
    assert promo_map["庆余"]["1001"]["daily"] == {"2026年05月26日": 12.0}
    assert promo_map["庆余"]["1002"]["daily"] == {"2026年05月03日": 8.0}


def test_load_promo_map_filename_date_fallback(engine, tmp_path):
    path = make_promo_xlsx(str(tmp_path / "推广报表_庆余_20260526.xlsx"), rows=[["1001", 15]])
    promo_map = engine.load_promo_map([path])
    assert promo_map["庆余"]["1001"]["total"] == 15.0
    assert promo_map["庆余"]["1001"]["daily"] == {"2026年05月26日": 15.0}


# ---------- load_subsidy_map ----------

def test_load_subsidy_map_no_file(engine, tmp_path):
    logs = []
    engine = ProfitEngine(log_cb=logs.append)
    assert engine.load_subsidy_map(str(tmp_path / "不存在.xlsx")) == {}
    assert any("跳过官补" in m for m in logs)


def test_load_subsidy_map_normal(engine, tmp_path):
    path = make_subsidy_xlsx(
        str(tmp_path / "官补映射表.xlsx"),
        headers=["链接id", "商家编码-规格维度", "官补金额", "起始日期", "结束日期"],
        rows=[
            ["1001.0", "SKU-A", 10, "2026/05/01", "2026/05/31"],
            ["1001", "SKU-B", 5.5, None, None],
            ["", "SKU-C", 1, None, None],
        ],
    )
    subsidy_map = engine.load_subsidy_map(path)
    assert "1001" in subsidy_map
    assert "1001.0" not in subsidy_map
    rules = subsidy_map["1001"]
    assert rules["SKU-A"] == [{"start": date(2026, 5, 1), "end": date(2026, 5, 31), "amount": 10.0}]
    assert rules["SKU-B"] == [{"start": None, "end": None, "amount": 5.5}]
    assert "SKU-C" not in rules


def test_load_subsidy_map_missing_headers_skipped(engine, tmp_path):
    logs = []
    engine = ProfitEngine(log_cb=logs.append)
    path = make_subsidy_xlsx(
        str(tmp_path / "官补映射表.xlsx"),
        headers=["链接id", "官补金额"],
        rows=[["1001", 10]],
    )
    assert engine.load_subsidy_map(path) == {}
    assert any("已跳过" in m for m in logs)


# ---------- load_sort_list ----------

def test_load_sort_list_no_file(engine, tmp_path):
    logs = []
    engine = ProfitEngine(log_cb=logs.append)
    assert engine.load_sort_list(str(tmp_path / "不存在.xlsx")) == []
    assert any("默认排序" in m for m in logs)


def test_load_sort_list_single_column(engine, tmp_path):
    path = make_sort_xlsx(
        str(tmp_path / "产品汇总表.xlsx"),
        values=["雅培金装", None, "摩可纳8号", ""],
    )
    order_list = engine.load_sort_list(path)
    assert order_list == ["雅培金装", "摩可纳8号"]
