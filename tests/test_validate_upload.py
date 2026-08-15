# -*- coding: utf-8 -*-
"""configs.validate_on_upload（上传预检）边界测试（docs/模块接口契约.md 第 4/12 节）

- 合法文件通过 / 缺必要表头拒绝（fixtures_gen 生成合法文件，手工构造缺列版本）
- 损坏文件（非 xlsx 文本、空工作簿）拒绝
- 大小写/空格/全角表头归一化行为
- 错误文案格式（缺失表头名；文件名——实现暂缺，见 xfail 用例）
- tmp_path 隔离，FileStorage 构造上传对象

已知偏差（是否修由集成阶段决定，此处以 xfail 表达契约预期，随实现修复自动翻绿）：
1. 引擎 load_* 接受别名表头（cost 的"商家编码-规格维度"、link 的"店铺"、
   promo 的"总花费"、subsidy 的"商家编码-规格维度"），预检仅接受契约精确表头
   → 别名文件被拒。subsidy 尤甚：fixtures_gen 默认官补表用"商家编码-规格维度"，
   gen_fixtures 生成的"合法夹具"上传即被预检拒绝。
2. 全角括号"总花费（元）"不匹配（引擎亦不支持，属超契约格式）。
3. 表头内部空格"sku 成本"不匹配（normalize 仅 strip 首尾空白 + lower）。
4. 错误文案不含文件名（仅含缺失表头名）。
"""
import io
import os
import sys

import pytest
import openpyxl
from werkzeug.datastructures import FileStorage

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROFIT_SERVICE_DIR = os.path.join(TESTS_DIR, "..", "profit_service")
if PROFIT_SERVICE_DIR not in sys.path:
    sys.path.insert(0, PROFIT_SERVICE_DIR)
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)

import configs
from fixtures_gen import (
    make_cost_xlsx,
    make_link_xlsx,
    make_promo_xlsx,
    make_subsidy_xlsx,
    make_sort_xlsx,
)

# 契约要求表头（docs 第 4 节 + configs._REQUIRED_HEADERS），硬编码避免自证
REQUIRED_HEADERS = {
    "cost": ["组合编码", "sku成本"],
    "link": ["店铺名称", "产品名称", "商品id"],
    "promo": ["商品ID", "总花费(元)"],
    "subsidy": ["链接id", "规格编码", "官补金额"],
}
VALID_HEADERS = {
    "cost": ["组合编码", "单品编码", "商品名称", "数量", "单品成本", "sku成本"],
    "link": ["店铺名称", "产品名称", "商品id"],
    "promo": ["商品ID", "总花费(元)"],
    "subsidy": ["链接id", "规格编码", "官补金额"],
}
CFG_TYPES = tuple(REQUIRED_HEADERS) + ("sort",)

_MAKERS = {
    "cost": make_cost_xlsx,
    "link": make_link_xlsx,
    "promo": make_promo_xlsx,
    "subsidy": make_subsidy_xlsx,
}


def _storage_from_maker(tmp_path, cfg_type, filename, headers=None, values=None):
    """用 fixtures_gen 生成 xlsx 并包装为 FileStorage 上传对象"""
    path = tmp_path / filename
    if cfg_type == "sort":
        make_sort_xlsx(str(path), values=values if values is not None else ["雅培金装", "摩可纳8号"])
    else:
        _MAKERS[cfg_type](str(path), headers=headers)
    return FileStorage(stream=io.BytesIO(path.read_bytes()), filename=filename)


def _storage_from_bytes(data, filename):
    return FileStorage(stream=io.BytesIO(data), filename=filename)


# ---------- 1. 合法文件通过 ----------

@pytest.mark.parametrize("cfg_type", ["cost", "link", "promo", "subsidy"])
def test_valid_file_passes(cfg_type, tmp_path):
    fs = _storage_from_maker(tmp_path, cfg_type, f"{cfg_type}_合法.xlsx", headers=VALID_HEADERS[cfg_type])
    ok, msg = configs.validate_on_upload(cfg_type, fs)
    assert ok, msg


def test_sort_valid_passes(tmp_path):
    fs = _storage_from_maker(tmp_path, "sort", "sort_合法.xlsx", values=["雅培金装", "摩可纳8号"])
    ok, msg = configs.validate_on_upload("sort", fs)
    assert ok, msg


# ---------- 2. 缺必要表头拒绝 ----------

@pytest.mark.parametrize(
    "cfg_type,missing",
    [(t, m) for t, reqs in REQUIRED_HEADERS.items() for m in reqs],
    ids=[f"{t}-缺{m}" for t, reqs in REQUIRED_HEADERS.items() for m in reqs],
)
def test_missing_required_header_rejected(cfg_type, missing, tmp_path):
    headers = [h for h in VALID_HEADERS[cfg_type] if h.lower() != missing.lower()]
    fs = _storage_from_maker(tmp_path, cfg_type, f"{cfg_type}_缺{missing}.xlsx", headers=headers)
    ok, msg = configs.validate_on_upload(cfg_type, fs)
    assert not ok
    assert "缺少必要表头" in msg
    assert missing in msg


# ---------- 3. 别名表头（引擎 load_* 候选名，契约预期应过） ----------

@pytest.mark.xfail(reason="偏差#1：预检不认引擎别名\"商家编码-规格维度\"（cost sku 列）", strict=False)
def test_cost_alias_sku_column_passes(tmp_path):
    fs = _storage_from_maker(
        tmp_path, "cost", "cost_别名.xlsx",
        headers=["商家编码-规格维度", "单品编码", "商品名称", "数量", "单品成本", "sku成本"],
    )
    ok, msg = configs.validate_on_upload("cost", fs)
    assert ok, msg


@pytest.mark.xfail(reason="偏差#1：预检不认引擎别名\"店铺\"", strict=False)
def test_link_alias_store_passes(tmp_path):
    fs = _storage_from_maker(tmp_path, "link", "link_别名.xlsx", headers=["店铺", "产品名称", "商品id"])
    ok, msg = configs.validate_on_upload("link", fs)
    assert ok, msg


def test_promo_alias_product_id_case_passes(tmp_path):
    """小写商品id：大小写归一化已支持，应直接通过"""
    fs = _storage_from_maker(tmp_path, "promo", "promo_商品id.xlsx", headers=["商品id", "总花费(元)"])
    ok, msg = configs.validate_on_upload("promo", fs)
    assert ok, msg


@pytest.mark.xfail(reason="偏差#1：预检不认引擎别名\"总花费\"（缺\"总花费(元)\"）", strict=False)
def test_promo_alias_total_cost_passes(tmp_path):
    fs = _storage_from_maker(tmp_path, "promo", "promo_总花费.xlsx", headers=["商品ID", "总花费"])
    ok, msg = configs.validate_on_upload("promo", fs)
    assert ok, msg


@pytest.mark.xfail(
    reason="偏差#1：fixtures_gen 默认官补表用\"商家编码-规格维度\"，预检缺\"规格编码\"拒（引擎可读）",
    strict=False,
)
def test_subsidy_alias_sku_column_passes(tmp_path):
    fs = _storage_from_maker(
        tmp_path, "subsidy", "官补映射表.xlsx",
        headers=["链接id", "商家编码-规格维度", "官补金额"],
    )
    ok, msg = configs.validate_on_upload("subsidy", fs)
    assert ok, msg


# ---------- 4. 大小写/空格/全角表头归一化 ----------

@pytest.mark.parametrize("cfg_type,headers", [
    ("promo", ["商品ID ", "总花费(元)"]),
    ("cost", ["组合编码", "单品编码", "商品名称", "数量", "单品成本", "sku成本 "]),
])
def test_trailing_space_header_passes(cfg_type, headers, tmp_path):
    """首尾空格 strip 后应匹配"""
    fs = _storage_from_maker(tmp_path, cfg_type, f"{cfg_type}_空格.xlsx", headers=headers)
    ok, msg = configs.validate_on_upload(cfg_type, fs)
    assert ok, msg


@pytest.mark.xfail(reason="偏差#3：normalize 仅 strip 首尾空白，内部空格\"sku 成本\"不匹配", strict=False)
def test_internal_space_header_matches(tmp_path):
    fs = _storage_from_maker(
        tmp_path, "cost", "cost_内空格.xlsx",
        headers=["组合编码", "单品编码", "商品名称", "数量", "单品成本", "sku 成本"],
    )
    ok, msg = configs.validate_on_upload("cost", fs)
    assert ok, msg


@pytest.mark.xfail(reason="偏差#2：全角括号\"总花费（元）\"不匹配（引擎亦不支持，属超契约格式）", strict=False)
def test_fullwidth_header_matches(tmp_path):
    fs = _storage_from_maker(tmp_path, "promo", "promo_全角.xlsx", headers=["商品ID", "总花费（元）"])
    ok, msg = configs.validate_on_upload("promo", fs)
    assert ok, msg


# ---------- 5. 错误文案格式 ----------

def test_error_message_contains_missing_header_name(tmp_path):
    fs = _storage_from_maker(tmp_path, "link", "缺商品id.xlsx", headers=["店铺名称", "产品名称"])
    ok, msg = configs.validate_on_upload("link", fs)
    assert not ok
    assert "缺少必要表头" in msg
    assert "商品id" in msg


@pytest.mark.xfail(reason="偏差#4：预检文案不含文件名（仅含缺失表头名）", strict=False)
def test_error_message_contains_filename(tmp_path):
    fs = _storage_from_maker(tmp_path, "cost", "缺sku成本.xlsx", headers=["组合编码"])
    ok, msg = configs.validate_on_upload("cost", fs)
    assert not ok
    assert "缺sku成本.xlsx" in msg


# ---------- 6. 损坏文件 ----------

def test_non_xlsx_text_rejected():
    fs = _storage_from_bytes("这是一段文本，不是 xlsx".encode("utf-8"), "fake.xlsx")
    ok, msg = configs.validate_on_upload("cost", fs)
    assert not ok
    assert "无法解析 Excel 文件" in msg


@pytest.mark.parametrize("cfg_type", CFG_TYPES)
def test_empty_workbook_no_header_rejected(cfg_type, tmp_path):
    wb = openpyxl.Workbook()  # 空工作簿：无表头行
    p = tmp_path / "empty.xlsx"
    wb.save(str(p))
    fs = _storage_from_bytes(p.read_bytes(), "empty.xlsx")
    ok, msg = configs.validate_on_upload(cfg_type, fs)
    assert not ok
    if cfg_type == "sort":
        assert "首列" in msg
    else:
        assert "缺少必要表头" in msg


# ---------- 7. sort 首列校验 ----------

def test_sort_first_cell_empty_rejected(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.append(["", "备用列"])
    p = tmp_path / "sort_empty_first.xlsx"
    wb.save(str(p))
    fs = _storage_from_bytes(p.read_bytes(), "sort_empty_first.xlsx")
    ok, msg = configs.validate_on_upload("sort", fs)
    assert not ok
    assert "首列" in msg


# ---------- 8. 未知类型 ----------

def test_unknown_cfg_type_rejected():
    fs = _storage_from_bytes(b"", "t.xlsx")
    ok, msg = configs.validate_on_upload("不存在的类型", fs)
    assert not ok
    assert "未知配置类型" in msg
