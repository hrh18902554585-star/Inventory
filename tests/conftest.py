# -*- coding: utf-8 -*-
"""pytest 共享夹具
- fixtures_dir：session 级，调用 gen_fixtures 生成到临时目录
- tmp_output：函数级临时输出目录
- monkeypatch_paths：把 profit_service 各模块目录常量 patch 到临时目录
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PROFIT_DIR = os.path.join(PROJECT_ROOT, "..", "profit_service")
sys.path.insert(0, PROFIT_DIR)  # 让测试可直接 import 各模块

import pytest

from fixtures_gen import gen_fixtures


@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory):
    """生成全部夹具到 session 级临时目录，返回目录路径"""
    return gen_fixtures(str(tmp_path_factory.mktemp("fixtures")))


@pytest.fixture
def tmp_output(tmp_path):
    """函数级输出目录 tmp_path/outputs"""
    out = tmp_path / "outputs"
    out.mkdir(exist_ok=True)
    return str(out)


@pytest.fixture
def monkeypatch_paths(monkeypatch, tmp_path):
    """把 db.DB_PATH / logging_setup.BASE_DIR 等目录常量 patch 到临时目录"""
    import db
    import logging_setup

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    db_path = str(data_dir / "app.db")
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "_ACTIVE_DB", db_path)
    db.init_db(db_path)  # 用临时库建表
    monkeypatch.setattr(logging_setup, "BASE_DIR", str(tmp_path))
