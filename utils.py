"""通用工具函式。"""

from datetime import date
from flask import jsonify


def api_response(code: int, message: str, data=None):
    """回傳統一封裝的 JSON 回應。"""
    body = {
        "code": code,
        "message": message,
        "data": data,
    }
    return jsonify(body), code


def get_period_key(issued_on: date) -> str:
    """由開立日決定期別。

    1–2 月為 YYYY-01，3–4 月為 YYYY-03，直到 11–12 月為 YYYY-11。
    """
    period_month = ((issued_on.month - 1) // 2) * 2 + 1
    return f"{issued_on.year}-{period_month:02d}"


def get_period_date_range(period_key: str):
    """由期別字串取得該期的起訖日期範圍 [start_date, next_start_date)。"""
    if not isinstance(period_key, str):
        return None, None
    parts = period_key.strip().split("-")
    if len(parts) != 2:
        return None, None
    try:
        year = int(parts[0])
        start_month = int(parts[1])
    except ValueError:
        return None, None

    if start_month not in (1, 3, 5, 7, 9, 11):
        return None, None

    start_date = date(year, start_month, 1)
    if start_month == 11:
        next_start = date(year + 1, 1, 1)
    else:
        next_start = date(year, start_month + 2, 1)

    return start_date, next_start

