# -*- coding: utf-8 -*-
"""配置/上传接口 API 集成测试（按 docs/模块接口契约.md 第 9/3/4/5 节）

- fixture tmp_data: monkeypatch db.DB_PATH / configs.CONFIGS_DIR /
  files_store.UPLOADS_DIR / security.TOKEN_FILE 指向 pytest tmp_path
- fixture client: create_app().test_client()，自动附带 X-Api-Token
- 上传文件用 werkzeug.datastructures.FileStorage(BytesIO, filename=...) 构造

当前状态：app.py / configs.py / files_store.py / security.py 尚未实现，
此文件按契约预写，模块落地后应直接全绿。
"""
import io
import os
import sys

import pytest
from werkzeug.datastructures import FileStorage

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROFIT_SERVICE_DIR = os.path.join(TESTS_DIR, "..", "profit_service")
if PROFIT_SERVICE_DIR not in sys.path:
    sys.path.insert(0, PROFIT_SERVICE_DIR)
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)

from fixtures_gen import make_cost_xlsx, make_order_csv
# 顶层名导入（与 app.py 内部 import db/configs/security 一致），
# 避免 profit_service.security 与 security 双实例导致 monkeypatch 失效
import configs
import db
import files_store
import security

CONFIG_TYPES = ("cost", "link", "promo", "subsidy", "sort")


class _AuthedClient:
    """包装 test_client：请求自动附带 X-Api-Token，显式传入的 headers 优先"""

    def __init__(self, inner, token):
        self._inner = inner
        self._token = token

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def _apply(self, kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        headers.setdefault("X-Api-Token", self._token)
        kwargs["headers"] = headers
        return kwargs

    def get(self, *args, **kwargs):
        return self._inner.get(*args, **self._apply(kwargs))

    def post(self, *args, **kwargs):
        return self._inner.post(*args, **self._apply(kwargs))

    def delete(self, *args, **kwargs):
        return self._inner.delete(*args, **self._apply(kwargs))


@pytest.fixture
def tmp_data(tmp_path, monkeypatch):
    """把 profit_service 各模块的目录/文件常量指向 tmp 目录"""
    data_dir = tmp_path / "data"
    monkeypatch.setattr(db, "DB_PATH", str(data_dir / "app.db"))
    monkeypatch.setattr(configs, "CONFIGS_DIR", str(data_dir / "configs"))
    monkeypatch.setattr(files_store, "UPLOADS_DIR", str(data_dir / "uploads"))
    monkeypatch.setattr(security, "TOKEN_FILE", str(data_dir / "token.txt"))
    # app 模块的 COOKIE_FILE 是模块级常量（BASE_DIR 拼接），需同样指向 tmp
    import app as app_mod
    monkeypatch.setattr(app_mod, "COOKIE_FILE", str(data_dir / "cookie.txt"))
    # 模拟 run.py 启动初始化（create_app 不负责 init_db）
    db.init_db(db.DB_PATH)
    return data_dir


def _create_flask_app():
    # app 延迟 import：确保在 monkeypatch 之后、且顶层若存在 create_app()
    # 调用也落在 tmp 目录
    from profit_service import app as app_mod
    return app_mod.create_app()


@pytest.fixture
def client(tmp_data):
    """带 token 的 test_client"""
    flask_app = _create_flask_app()
    token = security.get_token()
    return _AuthedClient(flask_app.test_client(), token)


@pytest.fixture
def bare_client(tmp_data):
    """不带 token 的原始 test_client（401 用例）"""
    return _create_flask_app().test_client()


def _upload(client, url, filename, data_bytes, type_=None):
    fs = FileStorage(stream=io.BytesIO(data_bytes), filename=filename)
    payload = {"file": fs}
    if type_ is not None:
        payload["type"] = type_
    return client.post(url, data=payload, content_type="multipart/form-data")


def _cost_xlsx_bytes():
    buf = io.BytesIO()
    make_cost_xlsx(buf)
    return buf.getvalue()


def _order_csv_bytes(rows=None):
    rows = rows or [["20260001", "已发货，待收货", "1001", "SKU-A", 2, 200, 10, "2026-08-15 10:00:00"]]
    buf = io.StringIO()
    make_order_csv(buf, rows)
    return buf.getvalue().encode("utf-8")


# ---------- 用例 ----------

def test_configs_requires_token(bare_client):
    """未带 token 访问 /api/configs → 401 code=1"""
    r = bare_client.get("/api/configs")
    assert r.status_code == 401
    body = r.get_json()
    assert body["code"] == 1
    assert "未授权" in body.get("message", "")


def test_configs_empty_initially(client):
    """带 token: 初始各配置类型均为空"""
    r = client.get("/api/configs")
    assert r.status_code == 200
    body = r.get_json()
    assert body["code"] == 0
    data = body["data"]
    for cfg_type in CONFIG_TYPES:
        entry = data[cfg_type]
        assert entry["current"] is None, cfg_type
        assert entry["versions"] == [], cfg_type


def test_config_upload_versioning(client):
    """上传合法成本表 → version=1；重复上传 → version=2 且旧版保留"""
    r1 = _upload(client, "/api/configs/upload", "成本表.xlsx", _cost_xlsx_bytes(), type_="cost")
    assert r1.status_code == 200
    b1 = r1.get_json()
    assert b1["code"] == 0
    rec1 = b1["data"]["uploaded"][0]
    assert rec1["type"] == "cost"
    assert rec1["version"] == 1

    r2 = _upload(client, "/api/configs/upload", "成本表.xlsx", _cost_xlsx_bytes(), type_="cost")
    assert r2.status_code == 200
    rec2 = r2.get_json()["data"]["uploaded"][0]
    assert rec2["version"] == 2

    body = client.get("/api/configs").get_json()["data"]["cost"]
    assert body["current"]["version"] == 2
    versions = [v["version"] for v in body["versions"]]
    assert versions == [2, 1]


def test_config_upload_invalid_file(client):
    """非法文件上传 → 校验失败 code=5"""
    r1 = _upload(client, "/api/configs/upload", "成本表.xlsx", b"not an xlsx at all", type_="cost")
    assert r1.status_code == 200
    assert r1.get_json()["code"] == 5

    r2 = _upload(client, "/api/configs/upload", "evil.txt", b"PK\x03\x04fake", type_="cost")
    assert r2.status_code == 200
    assert r2.get_json()["code"] == 5


def test_uploads_crud(client, tmp_data):
    """上传订单 CSV → 返回记录；GET 列表可见；DELETE 删除"""
    r = client.post("/api/uploads", data={
        "file": FileStorage(stream=io.BytesIO(_order_csv_bytes()), filename="庆余订单_20260815.csv"),
    }, content_type="multipart/form-data")
    assert r.status_code == 200
    rec = r.get_json()["data"]["uploaded"][0]
    assert rec["id"].startswith("f_")
    assert rec["name"].endswith(".csv")
    fid = rec["id"]

    items = client.get("/api/uploads").get_json()["data"]
    assert any(i["id"] == fid for i in items)

    d = client.delete(f"/api/uploads/{fid}")
    assert d.status_code == 200
    assert d.get_json()["code"] == 0

    after = client.get("/api/uploads").get_json()["data"]
    assert all(i["id"] != fid for i in after)


def test_upload_filename_sanitized(client, tmp_data):
    """路径穿越文件名被清洗，落盘于 uploads 目录内"""
    r = client.post("/api/uploads", data={
        "file": FileStorage(stream=io.BytesIO(_order_csv_bytes()), filename="../../../etc/passwd.csv"),
    }, content_type="multipart/form-data")
    assert r.status_code == 200
    rec = r.get_json()["data"]["uploaded"][0]
    name = rec["name"]
    assert "/" not in name and "\\" not in name and ".." not in name

    uploads_dir = str(tmp_data / "uploads")
    saved = os.path.join(uploads_dir, name)
    assert os.path.normpath(saved).startswith(os.path.normpath(uploads_dir))
    assert os.path.exists(saved)


def test_cookie_rw(client):
    """POST /api/cookie 写入；GET /api/cookie 返回脱敏信息，不回传明文"""
    r = client.post("/api/cookie", json={"cookie": "session=abc123"})
    assert r.status_code == 200
    b = r.get_json()
    assert b["code"] == 0
    assert b["data"].get("success") is True

    g = client.get("/api/cookie")
    assert g.status_code == 200
    info = g.get_json()["data"]
    assert "cookie_valid" in info
    assert "masked" in info
    assert "updated_at" in info
    assert info["masked"] != "session=abc123"
