# -*- coding: utf-8 -*-
"""利润核算引擎工具方法单元测试
覆盖: normalize_header / find_header_index / to_float / clean_id /
      parse_excluded_product_ids / parse_cost_date_range / parse_date /
      extract_store_name / extract_date_from_filename / get_sort_key
断言均按 engine.py 当前实现的实际行为编写。
"""
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "profit_service"))

import pytest

from engine import ProfitEngine


@pytest.fixture
def engine():
    return ProfitEngine()


# ---------- normalize_header ----------
class TestNormalizeHeader:
    def test_none_返回空串(self, engine):
        assert engine.normalize_header(None) == ""

    def test_首尾空格与大小写归一(self, engine):
        assert engine.normalize_header("  商品ID  ") == "商品id"

    def test_英文字母转小写(self, engine):
        assert engine.normalize_header("ProductID") == "productid"

    def test_数字转字符串(self, engine):
        assert engine.normalize_header(123) == "123"

    def test_中间空格保留(self, engine):
        assert engine.normalize_header(" 商家 编码 ") == "商家 编码"


# ---------- find_header_index ----------
class TestFindHeaderIndex:
    def test_别名匹配归一化键重复时取最后列(self, engine):
        headers = ["商品id", "商品ID", "链接id"]
        assert engine.find_header_index(headers, ["商品ID"]) == 1

    def test_候选按顺序首个命中即返回(self, engine):
        headers = ["订单号", "商品ID"]
        assert engine.find_header_index(headers, ["链接id", "商品ID"]) == 1

    def test_表头大小写空格归一后匹配(self, engine):
        headers = ["  商品ID  ", "销售额"]
        assert engine.find_header_index(headers, ["商品id"]) == 0

    def test_数字表头归一匹配(self, engine):
        headers = ["商品ID", 123, "备注"]
        assert engine.find_header_index(headers, ["123"]) == 1

    def test_无匹配返回None(self, engine):
        assert engine.find_header_index(["订单号", "订单状态"], ["商品ID"]) is None

    def test_空表头返回None(self, engine):
        assert engine.find_header_index([], ["商品ID"]) is None

    def test_None表头值不抛异常(self, engine):
        assert engine.find_header_index([None, "商品ID"], ["商品id"]) == 1


# ---------- to_float ----------
class TestToFloat:
    def test_None返回0(self, engine):
        assert engine.to_float(None) == 0.0

    def test_空串返回0(self, engine):
        assert engine.to_float("") == 0.0

    def test_纯空白返回0(self, engine):
        assert engine.to_float("   ") == 0.0

    def test_普通小数(self, engine):
        assert engine.to_float("123.45") == 123.45

    def test_前后空格自动去除(self, engine):
        assert engine.to_float("  42  ") == 42.0

    def test_英文逗号千分位(self, engine):
        assert engine.to_float("1,234.56") == 1234.56

    def test_中文逗号千分位(self, engine):
        assert engine.to_float("1，234") == 1234.0

    def test_人民币符号全角(self, engine):
        assert engine.to_float("￥100") == 100.0

    def test_人民币符号半角(self, engine):
        assert engine.to_float("¥99.9") == 99.9

    def test_数字对象直接转换(self, engine):
        assert engine.to_float(3.14) == 3.14

    def test_非数字返回0(self, engine):
        assert engine.to_float("abc") == 0.0

    def test_混合脏字符返回0(self, engine):
        assert engine.to_float("¥1,234.5元") == 0.0


# ---------- clean_id ----------
class TestCleanId:
    def test_浮点样式去掉点零(self, engine):
        assert engine.clean_id("123.0") == "123"

    def test_普通id原样返回(self, engine):
        assert engine.clean_id("123") == "123"

    def test_None返回空串(self, engine):
        assert engine.clean_id(None) == ""

    def test_前后空格去除(self, engine):
        assert engine.clean_id("  123  ") == "123"

    def test_两位小数不以点零结尾则保留(self, engine):
        assert engine.clean_id("123.00") == "123.00"

    def test_最小点零边界(self, engine):
        assert engine.clean_id("1.0") == "1"


# ---------- parse_excluded_product_ids ----------
class TestParseExcludedProductIds:
    def test_None返回空集合(self, engine):
        assert engine.parse_excluded_product_ids(None) == set()

    def test_空串返回空集合(self, engine):
        assert engine.parse_excluded_product_ids("") == set()

    def test_逗号空格中文逗号混合(self, engine):
        assert engine.parse_excluded_product_ids("A,B C，D") == {"A", "B", "C", "D"}

    def test_多余空白与重复项去重(self, engine):
        assert engine.parse_excluded_product_ids("  A  ,  A ,B ") == {"A", "B"}


# ---------- parse_cost_date_range ----------
class TestParseCostDateRange:
    def test_空串返回空日期对(self, engine):
        assert engine.parse_cost_date_range("") == (None, None)

    def test_None返回空日期对(self, engine):
        assert engine.parse_cost_date_range(None) == (None, None)

    def test_斜杠日期范围正常解析(self, engine):
        assert engine.parse_cost_date_range("2026/1/1-2026/2/1") == (date(2026, 1, 1), date(2026, 2, 1))

    def test_点号与连字符日期正常解析(self, engine):
        assert engine.parse_cost_date_range("2026.1.1 - 2026.2.1") == (date(2026, 1, 1), date(2026, 2, 1))

    def test_连字符日期范围被拆分为多段返回空对(self, engine):
        assert engine.parse_cost_date_range("2026-01-01 - 2026-02-01") == (None, None)

    def test_结束为至今时结束日期为None(self, engine):
        assert engine.parse_cost_date_range("2026/1/1 - 至今") == (date(2026, 1, 1), None)

    def test_仅有至今无法拆分(self, engine):
        assert engine.parse_cost_date_range("至今") == (None, None)

    def test_非法月份返回空对(self, engine):
        assert engine.parse_cost_date_range("2026/13/1-2026/2/1") == (None, date(2026, 2, 1))

    def test_非法输入返回空对(self, engine):
        assert engine.parse_cost_date_range("非法输入") == (None, None)


# ---------- parse_date ----------
class TestParseDate:
    def test_datetime对象转date(self, engine):
        assert engine.parse_date(datetime(2026, 5, 6, 10, 30)) == date(2026, 5, 6)

    def test_连字符日期(self, engine):
        assert engine.parse_date("2026-05-06") == date(2026, 5, 6)

    def test_斜杠日期(self, engine):
        assert engine.parse_date("2026/05/06") == date(2026, 5, 6)

    def test_中文年月日(self, engine):
        assert engine.parse_date("2026年05月06日") == date(2026, 5, 6)

    def test_中文月日无前导零(self, engine):
        assert engine.parse_date("2026年5月6日") == date(2026, 5, 6)

    def test_字符串中混入其他文字(self, engine):
        assert engine.parse_date("支付时间 2026-05-06 12:00") == date(2026, 5, 6)

    def test_两位年份不匹配返回None(self, engine):
        assert engine.parse_date("26-5-6") is None

    def test_纯非法输入返回None(self, engine):
        assert engine.parse_date("abc") is None

    def test_None返回None(self, engine):
        assert engine.parse_date(None) is None

    def test_空串返回None(self, engine):
        assert engine.parse_date("") is None


# ---------- extract_store_name ----------
class TestExtractStoreName:
    def test_文件名含庆余店铺(self, engine):
        assert engine.extract_store_name(r"D:\data\庆余订单_20260815.csv") == "庆余"

    def test_文件名含雅丽丹店铺(self, engine):
        assert engine.extract_store_name("雅丽丹报表.xlsx") == "雅丽丹"

    def test_文件名含大咖猴店铺(self, engine):
        assert engine.extract_store_name(r"C:\dir\大咖猴_2026.csv") == "大咖猴"

    def test_文件名含趣味猴店铺(self, engine):
        assert engine.extract_store_name("趣味猴_20260501.csv") == "趣味猴"

    def test_文件名含品味店铺(self, engine):
        assert engine.extract_store_name("品味订单.xlsx") == "品味"

    def test_仅传文件名不取目录(self, engine):
        assert engine.extract_store_name("庆余.csv") == "庆余"

    def test_无店铺名返回未知店铺(self, engine):
        assert engine.extract_store_name("20260815.csv") == "未知店铺"

    def test_无店铺名带路径返回未知店铺(self, engine):
        assert engine.extract_store_name(r"D:\data\订单_20260815.csv") == "未知店铺"


# ---------- extract_date_from_filename ----------
class TestExtractDateFromFilename:
    def test_纯数字完整日期(self, engine):
        assert engine.extract_date_from_filename("庆余订单_20260815.csv") == "2026年08月15日"

    def test_连字符完整日期(self, engine):
        assert engine.extract_date_from_filename("2026-05-26.csv") == "2026年05月26日"

    def test_中文年月日完整日期(self, engine):
        assert engine.extract_date_from_filename("2026年5月6日.csv") == "2026年05月06日"

    def test_纯数字简写补20前缀(self, engine):
        assert engine.extract_date_from_filename("260526.csv") == "2026年05月26日"

    def test_连字符简写补20前缀(self, engine):
        assert engine.extract_date_from_filename("26-5-26.csv") == "2026年05月26日"

    def test_完整路径中的日期(self, engine):
        assert engine.extract_date_from_filename(r"D:\data\庆余_20260526.csv") == "2026年05月26日"

    def test_无日期返回空串(self, engine):
        assert engine.extract_date_from_filename("订单无日期.csv") == ""

    def test_无效月份纯数字不匹配(self, engine):
        assert engine.extract_date_from_filename("261326.csv") == ""


# ---------- get_sort_key ----------
class TestGetSortKey:
    def test_空排序表返回末位(self, engine):
        assert engine.get_sort_key("产品A", []) == (1, "产品A")

    def test_精确匹配返回首位(self, engine):
        assert engine.get_sort_key("产品A", ["产品A", "产品B"]) == (0, 0)

    def test_产品名被排序项包含(self, engine):
        assert engine.get_sort_key("苹果iPhone15", ["苹果iPhone15手机"]) == (0, 0)

    def test_排序项被产品名包含(self, engine):
        assert engine.get_sort_key("苹果iPhone15手机", ["苹果iPhone15"]) == (0, 0)

    def test_大小写空格归一后包含(self, engine):
        assert engine.get_sort_key("Apple iPhone", ["appleiphone"]) == (0, 0)

    def test_模糊相似度大于05命中(self, engine):
        assert engine.get_sort_key("华为P50Pro", ["华为P40"]) == (0, 0)

    def test_模糊相似度优先于更靠后的精确项(self, engine):
        assert engine.get_sort_key("华为P50Pro", ["无关产品", "华为P40"]) == (0, 1)

    def test_无匹配返回末位并保留原名(self, engine):
        assert engine.get_sort_key("ABCXYZ", ["QQQ"]) == (1, "ABCXYZ")

    def test_相似度不足05返回末位(self, engine):
        assert engine.get_sort_key("小米15", ["红米"]) == (1, "小米15")
