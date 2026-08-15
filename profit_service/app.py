# -*- coding: utf-8 -*-
"""Flask 路由层（契约第 9 节，集成所有子模块）

- 鉴权: 除 / 与 /static/* 外全部要求 X-Api-Token（401 + {"code":1,"message":"未授权"}）
- 统一响应: 成功 {"code":0,"data":...}；失败 {"code":xxx,"message":"中文"}
- 错误码: 1 未授权, 2 参数错误, 3 配置缺失, 4 任务不存在/非法, 5 上传校验失败, 6 服务忙(排队满)
- 启动时: init_db + tax_cache.load_cache + task_manager.init_task_manager + cleanup_outputs
"""
import os
import time

from flask import Flask, g, jsonify, render_template, request, send_from_directory

import configs
import db
import files_store
import security
import stats
import task_manager
import tax_cache
from logging_setup import get_logger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
COOKIE_FILE = os.path.join(DATA_DIR, "cookie.txt")

logger = get_logger()


def create_app() -> Flask:
    app = Flask(__name__)

    # ---- 启动初始化（路径常量可被测试 monkeypatch） ----
    os.makedirs(DATA_DIR, exist_ok=True)
    db.init_db(db.DB_PATH)
    tax_cache.load_cache(os.path.join(DATA_DIR, "tax_cache.json"))
    task_manager.init_task_manager()
    task_manager.cleanup_outputs()

    def ok(data=None):
        return jsonify({"code": 0, "data": security.sanitize_dict(data if data is not None else {})})

    def fail(code, message, http=200):
        resp = jsonify({"code": code, "message": message})
        resp.status_code = http
        return resp

    def _error_response(err: str):
        """task_manager 错误文案前缀 → 错误码（参数错误→2 / 配置缺失→3 / 服务忙→6 / 其他→4）"""
        if err.startswith("参数错误:"):
            return fail(2, err.split(": ", 1)[1])
        if err.startswith("配置缺失:"):
            return fail(3, err.split(": ", 1)[1])
        if err.startswith("服务忙:"):
            return fail(6, err.split(": ", 1)[1])
        return fail(4, err)

    # ---- 鉴权 + 请求日志 ----
    @app.before_request
    def _require_token():
        g._req_start = time.time()
        if request.path == "/" or request.path.startswith("/static"):
            return None
        if not security.check_request(request):
            return fail(1, "未授权", 401)
        return None

    @app.after_request
    def _log_response(resp):
        dur_ms = (time.time() - getattr(g, "_req_start", time.time())) * 1000
        msg = security.sanitize(f"{request.method} {request.path} -> {resp.status_code} ({dur_ms:.0f}ms)")
        logger.info(msg)
        return resp

    # ---- 首页 ----
    @app.get("/")
    def index():
        return render_template("index.html")

    # ---- Cookie ----
    @app.get("/api/cookie")
    def api_get_cookie():
        valid = os.path.exists(COOKIE_FILE)
        masked, updated_at = "", None
        if valid:
            with open(COOKIE_FILE, encoding="utf-8") as f:
                raw = f.read().strip()
            if len(raw) >= 4:
                masked = raw[:2] + "***" + raw[-2:]
            elif raw:
                masked = "***"
            updated_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(COOKIE_FILE)))
        return ok({"cookie_valid": valid, "masked": masked, "updated_at": updated_at})

    @app.post("/api/cookie")
    def api_set_cookie():
        data = request.get_json(silent=True) or {}
        cookie = str(data.get("cookie") or "").strip()
        if not cookie:
            return fail(2, "Cookie 不能为空")
        os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            f.write(cookie)
        logger.info(security.sanitize("已更新 cookie.txt"))
        return ok({"success": True})

    # ---- 配置 ----
    @app.get("/api/configs")
    def api_list_configs():
        return ok(configs.list_configs())

    @app.post("/api/configs/upload")
    def api_upload_config():
        cfg_type = request.form.get("type", "")
        if cfg_type not in configs.CONFIG_TYPES:
            return fail(2, f"未知配置类型: {cfg_type}")
        files = request.files.getlist("file") or request.files.getlist("files")
        if not files or not files[0].filename:
            return fail(2, "缺少上传文件")
        uploaded = []
        for f in files:
            ok_v, msg = configs.validate_on_upload(cfg_type, f)
            if not ok_v:
                return fail(5, f"{f.filename}: {msg}")
            ok_s, res = configs.save_config(cfg_type, f)
            if not ok_s:
                return fail(5, res)
            uploaded.append(res)
        return ok({"uploaded": uploaded})

    @app.delete("/api/configs")
    def api_delete_config():
        cfg_type = request.args.get("type", "")
        version_raw = request.args.get("version")
        version = None
        if version_raw is not None:
            try:
                version = int(version_raw)
            except ValueError:
                return fail(2, "version 必须是整数")
        ok_d, msg = configs.delete_config(cfg_type, version)
        if not ok_d:
            return fail(4, msg, 404)
        return ok({"deleted": cfg_type, "version": version})

    # ---- 订单文件 ----
    @app.post("/api/uploads")
    def api_upload_order_file():
        files = request.files.getlist("file") or request.files.getlist("files")
        if not files or not files[0].filename:
            return fail(2, "缺少上传文件")
        uploaded = []
        for f in files:
            ok_v, msg = files_store.validate_upload_file(f)
            if not ok_v:
                return fail(5, f"{f.filename}: {msg}")
            rec = files_store.save_order_file(f)
            if rec is None:
                return fail(5, f"{f.filename}: 文件保存失败")
            uploaded.append(rec)
        return ok({"uploaded": uploaded})

    @app.get("/api/uploads")
    def api_list_uploads():
        return ok(files_store.list_order_files())

    @app.delete("/api/uploads/<file_id>")
    def api_delete_upload(file_id):
        ok_d, msg = files_store.delete_order_file(file_id)
        if not ok_d:
            return fail(4, msg, 404)
        return ok({"deleted": file_id})

    # ---- 任务 ----
    @app.post("/api/jobs")
    def api_create_job():
        params = request.get_json(silent=True)
        if not isinstance(params, dict):
            return fail(2, "请求体必须是 JSON 对象")
        if not str(params.get("cookie") or "").strip():
            return fail(2, "Cookie 不能为空")
        if not isinstance(params.get("order_files"), list) or not params.get("order_files"):
            return fail(2, "至少选择一个订单文件")
        if not isinstance(params.get("configs"), dict):
            return fail(2, "配置参数非法")
        task_id, err = task_manager.submit_job(params)
        if err:
            return _error_response(err)
        return ok({"task_id": task_id})

    @app.get("/api/jobs")
    def api_list_jobs():
        jobs = []
        for t in task_manager.list_jobs():
            # 剔除 params_json（含 cookie）与 log_json，防泄露且更轻
            jobs.append({
                "id": t["id"], "status": t["status"], "progress": t["progress"],
                "status_text": t["status_text"],
                "result_files": t["result_files_json"], "created_at": t["created_at"],
                "finished_at": t["finished_at"], "error": t["error"],
            })
        return ok(jobs)

    @app.get("/api/jobs/<task_id>")
    def api_get_job(task_id):
        since_raw = request.args.get("since", "0")
        try:
            since = max(0, int(since_raw))
        except ValueError:
            return fail(2, "since 必须是整数")
        task = task_manager.get_job(task_id)
        if task is None:
            return fail(4, "任务不存在", 404)
        return ok({
            "id": task["id"], "status": task["status"], "progress": task["progress"],
            "status_text": task["status_text"], "created_at": task["created_at"],
            "finished_at": task["finished_at"], "error": task["error"],
            "result_files": task["result_files_json"],
            "logs": db.get_logs(task_id, since),
        })

    @app.post("/api/jobs/<task_id>/rerun")
    def api_rerun_job(task_id):
        new_id, err = task_manager.rerun_job(task_id)
        if err:
            return _error_response(err)
        return ok({"task_id": new_id})

    @app.delete("/api/jobs/<task_id>")
    def api_delete_job(task_id):
        ok_d, msg = task_manager.delete_job(task_id)
        if not ok_d:
            return fail(4, msg, 409 if "运行中" in msg else 404)
        return ok({"deleted": task_id})

    @app.get("/api/jobs/<task_id>/download/<filename>")
    def api_download(task_id, filename):
        # 文件名白名单/存在性由 task_manager.get_download_path 校验
        path = task_manager.get_download_path(task_id, filename)
        if path is None:
            return fail(4, "文件不存在或任务未完成", 404)
        return send_from_directory(os.path.dirname(path), os.path.basename(path),
                                   as_attachment=True, download_name=filename)

    # ---- 统计 ----
    @app.get("/api/stats")
    def api_stats():
        return ok(stats.get_stats())

    # ---- 404 兜底 ----
    @app.errorhandler(404)
    def not_found(e):
        return fail(4, "接口不存在", 404)

    return app
