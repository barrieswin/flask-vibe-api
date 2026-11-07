"""個人記帳本後端 RESTful API。

採用 Application Factory 模式，並透過 Flask-SQLAlchemy 連接 PostgreSQL。
"""

import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify
from sqlalchemy import text

from extensions import db


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

    def api_response(code: int, message: str, data=None):
        """回傳統一封裝的 JSON 回應。"""
        body = {
            "code": code,
            "message": message,
            "data": data,
        }
        return jsonify(body), code

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

    @app.errorhandler(404)
    def handle_not_found(_error):
        """找不到路徑時回傳 JSON 404。"""
        return api_response(404, "找不到這一筆", None)

    @app.errorhandler(405)
    def handle_method_not_allowed(_error):
        return api_response(405, "不支援的請求方法", None)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

