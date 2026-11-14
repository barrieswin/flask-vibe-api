"""通用工具函式。"""

from flask import jsonify


def api_response(code: int, message: str, data=None):
    """回傳統一封裝的 JSON 回應。"""
    body = {
        "code": code,
        "message": message,
        "data": data,
    }
    return jsonify(body), code
