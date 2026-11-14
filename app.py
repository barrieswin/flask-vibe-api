"""個人記帳本後端 RESTful API。

採用 Application Factory 模式，並透過 Flask-SQLAlchemy 連接 PostgreSQL。
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from extensions import db
from routes import (
    accounts_bp,
    draw_periods_bp,
    expense_categories_bp,
    expenses_bp,
    income_categories_bp,
    incomes_bp,
    instruments_bp,
    invoices_bp,
    summary_bp,
    trades_bp,
    transfers_bp,
)
from utils import api_response


def create_app() -> Flask:
    """建立並設定 Flask 應用程式實例。"""
    # 優先嘗試從專案根目錄的 .env 載入環境變數（若本機存在）
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)

    database_url = os.getenv("DATABASE_URL")
    if not database_url or not database_url.strip():
        raise RuntimeError(
            "未設定環境變數 DATABASE_URL，無法啟動伺服器。請在環境變數或專案根目錄的 .env 中指定 PostgreSQL 連線字串。"
        )

    # 若連線字串以 postgres:// 開頭，轉換為 SQLAlchemy 支援的 postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    allowed_origin_pattern = re.compile(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$")
    web_origin = os.getenv("WEB_ORIGIN", "").strip()

    def is_origin_allowed(origin: str | None) -> bool:
        if not origin:
            return False
        if allowed_origin_pattern.match(origin):
            return True
        if web_origin and origin == web_origin:
            return True
        return False

    @app.before_request
    def handle_cors_preflight():
        if request.method == "OPTIONS":
            origin = request.headers.get("Origin")
            res = Response(status=204)
            if is_origin_allowed(origin):
                res.headers["Access-Control-Allow-Origin"] = origin
                res.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, PUT, DELETE, OPTIONS"
                req_headers = request.headers.get("Access-Control-Request-Headers")
                if req_headers:
                    res.headers["Access-Control-Allow-Headers"] = req_headers
                else:
                    res.headers["Access-Control-Allow-Headers"] = "Content-Type"
                res.headers["Access-Control-Max-Age"] = "86400"
            res.headers["Access-Control-Allow-Private-Network"] = "true"
            res.headers["Vary"] = "Origin"
            res.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            return res

    @app.after_request
    def apply_cors_headers(response):
        origin = request.headers.get("Origin")
        if is_origin_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, PUT, DELETE, OPTIONS"
            req_headers = request.headers.get("Access-Control-Request-Headers")
            if req_headers:
                response.headers["Access-Control-Allow-Headers"] = req_headers
            else:
                response.headers["Access-Control-Allow-Headers"] = "Content-Type"

        # 一般回應與 preflight 都加上 Access-Control-Allow-Private-Network: true
        # 回應帶 Vary: Origin 與 Cache-Control: no-store, no-cache, must-revalidate
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        response.headers["Vary"] = "Origin"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response

    # 註冊 API 路由藍圖
    app.register_blueprint(accounts_bp)
    app.register_blueprint(transfers_bp)
    app.register_blueprint(income_categories_bp)
    app.register_blueprint(incomes_bp)
    app.register_blueprint(expense_categories_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(invoices_bp)
    app.register_blueprint(draw_periods_bp)
    app.register_blueprint(instruments_bp)
    app.register_blueprint(trades_bp)
    app.register_blueprint(summary_bp)

    @app.get("/api/health")
    def health_check():
        """回傳伺服器運行狀態與當前 UTC 時間（不查詢資料庫）。"""
        payload = {
            "status": "ok",
            "time": datetime.now(timezone.utc).isoformat(),
        }
        return api_response(200, "伺服器運作正常，測試正常可以進行其他任務。", payload)

    @app.get("/api/health/db")
    def db_health_check():
        """向 PostgreSQL 執行一次 SELECT 1 以檢查資料庫連線狀況。"""
        try:
            db.session.execute(text("SELECT 1"))
            return api_response(200, "資料庫連線正常", {"status": "ok"})
        except Exception as exc:
            app.logger.exception("資料庫連線檢查失敗: %s", exc)
            return api_response(500, "資料庫暫時連不上", None)

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(exc):
        """資料庫約束違反時回傳 400，不將資料庫表名或約束名暴露給客戶端。"""
        db.session.rollback()
        app.logger.warning("資料庫約束衝突: %s", exc)
        return api_response(400, "資料驗證失敗或違反約束規則", None)

    @app.errorhandler(OperationalError)
    def handle_operational_error(exc):
        """資料庫連線失敗時回傳 500。"""
        db.session.rollback()
        app.logger.exception("資料庫連線異常: %s", exc)
        return api_response(500, "資料庫連線失敗，請稍後再試", None)

    @app.errorhandler(404)
    def handle_not_found(_error):
        """找不到路徑時回傳 JSON 404。"""
        return api_response(404, "找不到指定的資源", None)

    @app.errorhandler(405)
    def handle_method_not_allowed(_error):
        return api_response(405, "不支援的請求方法", None)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

