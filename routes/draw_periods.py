"""統一發票開獎期別與獎號相關 API 路由。"""

import re
from datetime import datetime, timezone
from decimal import Decimal

from flask import Blueprint, request

from extensions import db
from models import DrawPeriod, DrawPrize, Invoice
from routes.invoices import _find_matching_prizes
from utils import api_response, get_period_date_range

draw_periods_bp = Blueprint("draw_periods", __name__, url_prefix="/api/draw-periods")

ALLOWED_TIERS = {
    "special",
    "grand",
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "extra_sixth",
}
EIGHT_DIGIT_TIERS = {"special", "grand", "first"}


@draw_periods_bp.post("")
def create_draw_period():
    """建立一期開獎期別。必填 period_key。成功回傳 201。"""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_response(400, "請提供合法的 JSON 物件格式", None)

    period_key_raw = payload.get("period_key")
    if not isinstance(period_key_raw, str) or not period_key_raw.strip():
        return api_response(400, "期別代碼為必填項目且不可為空", None)
    period_key = period_key_raw.strip()

    start_date, next_start = get_period_date_range(period_key)
    if not start_date or not next_start:
        return api_response(
            400, "期別代碼格式不符，應為 YYYY-MM 且月份為 01、03、05、07、09、11", None
        )

    # 檢查重複期別
    existing = db.session.scalar(
        db.select(DrawPeriod).filter_by(period_key=period_key)
    )
    if existing:
        return api_response(400, "該開獎期別已存在，不可重複建立", None)

    period = DrawPeriod(period_key=period_key)
    db.session.add(period)
    db.session.commit()

    return api_response(201, "開獎期別新增成功", period.to_dict())


@draw_periods_bp.post("/<int:period_id>/prizes")
def create_draw_prize(period_id: int):
    """新增一筆獎號與獎金。

    special、grand、first 的 matching_number 必須是 8 碼數字。
    金額不大於或等於 0 回傳 400。
    """
    period = db.session.get(DrawPeriod, period_id)
    if not period:
        return api_response(404, "找不到指定的開獎期別", None)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_response(400, "請提供合法的 JSON 物件格式", None)

    # 1. 必填 tier
    tier_raw = payload.get("tier")
    if not isinstance(tier_raw, str) or tier_raw.strip() not in ALLOWED_TIERS:
        return api_response(
            400,
            "獎項類別不在允許清單中，只允許 special、grand、first、second、third、fourth、fifth、sixth、extra_sixth",
            None,
        )
    tier = tier_raw.strip()

    # 2. 必填 matching_number
    matching_number_raw = payload.get("matching_number")
    if not isinstance(matching_number_raw, str) or not matching_number_raw.strip():
        return api_response(400, "中獎號碼為必填項目且不可為空", None)
    matching_number = matching_number_raw.strip()

    if tier in EIGHT_DIGIT_TIERS:
        if not re.match(r"^\d{8}$", matching_number):
            return api_response(
                400, "特別獎、特獎、頭獎的中獎號碼必須為 8 碼數字", None
            )
    else:
        if not re.match(r"^\d{3,8}$", matching_number):
            return api_response(400, "中獎號碼格式不符，必須為 3 到 8 碼純數字", None)

    # 3. 必填金額 amount (大於或等於 0)
    amount_raw = payload.get("amount")
    if amount_raw is None:
        return api_response(400, "獎金金額為必填項目", None)
    try:
        amount = Decimal(str(amount_raw))
    except (ValueError, TypeError, ArithmeticError):
        return api_response(400, "獎金金額必須為有效數值", None)
    if amount < 0:
        return api_response(400, "獎金金額必須大於或等於 0", None)

    # 檢查同一期、同一 tier、同一 matching_number 重複
    existing = db.session.scalar(
        db.select(DrawPrize).filter_by(
            draw_period_id=period.id,
            tier=tier,
            matching_number=matching_number,
        )
    )
    if existing:
        return api_response(400, "該期已存在相同的獎項與中獎號碼，不可重複", None)

    prize = DrawPrize(
        draw_period_id=period.id,
        tier=tier,
        matching_number=matching_number,
        amount=amount,
    )
    db.session.add(prize)
    db.session.commit()

    return api_response(201, "開獎獎項新增成功", prize.to_dict())


@draw_periods_bp.post("/<int:period_id>/check")
def check_draw_period_invoices(period_id: int):
    """對該期所有未作廢、且開立日落在該期的發票。

    依資料表裡的獎號與獎金對獎，回寫 prize_status。
    回傳對過的張數、中獎張數。
    """
    period = db.session.get(DrawPeriod, period_id)
    if not period:
        return api_response(404, "找不到指定的開獎期別", None)

    start_date, next_start = get_period_date_range(period.period_key)
    if not start_date or not next_start:
        return api_response(400, "開獎期別代碼格式不正確", None)

    # 取得本期已設定之所有獎號
    prizes = db.session.scalars(
        db.select(DrawPrize).filter_by(draw_period_id=period.id)
    ).all()

    # 查詢該期所有未作廢、且開立日落在該期的發票
    invoices = db.session.scalars(
        db.select(Invoice).where(
            Invoice.prize_status != "void",
            Invoice.issued_on >= start_date,
            Invoice.issued_on < next_start,
        )
    ).all()

    checked_count = 0
    won_count = 0

    for inv in invoices:
        checked_count += 1
        # 若發票已兌獎 (claimed)，保持 claimed 狀態並計入已中獎張數
        if inv.prize_status == "claimed":
            won_count += 1
            continue

        matched = _find_matching_prizes(inv.number, prizes)
        if matched:
            inv.prize_status = "won"
            won_count += 1
        else:
            inv.prize_status = "lost"

        inv.updated_at = datetime.now(timezone.utc)

    db.session.commit()

    return api_response(
        200,
        f"對獎完成，共對了 {checked_count} 張發票，中獎 {won_count} 張",
        {
            "checked_count": checked_count,
            "won_count": won_count,
        },
    )
