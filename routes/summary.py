"""月度生活現金流摘要 API 路由。"""

import re
from datetime import date
from decimal import Decimal

from flask import Blueprint, request

from extensions import db
from models import Expense, Income
from utils import api_response

summary_bp = Blueprint("summary", __name__, url_prefix="/api/summary")

MONTH_REGEX = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@summary_bp.get("")
def get_monthly_summary():
    """取得特定月份之生活現金流摘要（台幣合計）。

    查詢參數 month 必填，格式 YYYY-MM。
    回傳該月份之入帳合計（income_twd）與花費合計（expense_twd）。
    若無資料，兩者皆為 0，HTTP 狀態碼為 200。
    """
    month_raw = request.args.get("month")
    if not month_raw or not month_raw.strip():
        return api_response(400, "查詢參數 month 為必填項目，格式應為 YYYY-MM", None)

    month = month_raw.strip()
    if not MONTH_REGEX.match(month):
        return api_response(
            400, "月份格式不正確，格式應為 YYYY-MM（例如 2026-11）", None
        )

    year = int(month[:4])
    m = int(month[5:7])
    start_date = date(year, m, 1)
    if m == 12:
        next_month_start = date(year + 1, 1, 1)
    else:
        next_month_start = date(year, m + 1, 1)

    # 1. 入帳合計：received_on 落在該月的入帳，金額乘 fx_rate_to_twd 後加總
    incomes = db.session.scalars(
        db.select(Income).where(
            Income.received_on >= start_date,
            Income.received_on < next_month_start,
        )
    ).all()
    income_twd = sum(
        (inc.amount * inc.fx_rate_to_twd for inc in incomes), Decimal("0")
    )

    # 2. 花費合計：spent_on 落在該月的花費，金額乘 fx_rate_to_twd 後加總
    expenses = db.session.scalars(
        db.select(Expense).where(
            Expense.spent_on >= start_date,
            Expense.spent_on < next_month_start,
        )
    ).all()
    expense_twd = sum(
        (exp.amount * exp.fx_rate_to_twd for exp in expenses), Decimal("0")
    )

    data = {
        "month": month,
        "income_twd": float(round(income_twd, 4)),
        "expense_twd": float(round(expense_twd, 4)),
    }

    return api_response(200, "取得月度現金流摘要成功", data)
