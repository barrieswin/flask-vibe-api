"""移轉相關 API 路由。"""

from datetime import date
from decimal import Decimal

from flask import Blueprint, request

from extensions import db
from models import Account, Transfer
from utils import api_response

transfers_bp = Blueprint("transfers", __name__, url_prefix="/api/transfers")


@transfers_bp.get("")
def list_transfers():
    """取得移轉清單。若無資料回傳 200 與空清單。"""
    transfers = db.session.scalars(
        db.select(Transfer).order_by(Transfer.transferred_on.desc(), Transfer.id.desc())
    ).all()
    return api_response(200, "取得移轉清單成功", [t.to_dict() for t in transfers])


@transfers_bp.post("")
def create_transfer():
    """新增移轉。

    必填日期、金額、幣別、匯率、轉出帳戶、轉入帳戶。成功回傳 201。
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_response(400, "請提供合法的 JSON 物件格式", None)

    # 1. 必填日期 transferred_on
    transferred_on_raw = payload.get("transferred_on")
    if transferred_on_raw is None or not str(transferred_on_raw).strip():
        return api_response(400, "移轉日期為必填項目", None)
    try:
        transferred_on = date.fromisoformat(str(transferred_on_raw).strip())
    except (ValueError, TypeError):
        return api_response(400, "移轉日期格式不正確，請使用 YYYY-MM-DD 格式", None)

    # 2. 必填金額 amount (大於 0)
    amount_raw = payload.get("amount")
    if amount_raw is None:
        return api_response(400, "移轉金額為必填項目", None)
    try:
        amount = Decimal(str(amount_raw))
    except (ValueError, TypeError, ArithmeticError):
        return api_response(400, "移轉金額必須為有效數值", None)
    if amount <= 0:
        return api_response(400, "移轉金額必須大於 0", None)

    # 3. 必填幣別 currency (三碼)
    currency_raw = payload.get("currency")
    if currency_raw is None or not isinstance(currency_raw, str) or len(currency_raw.strip()) != 3:
        return api_response(400, "幣別代碼為必填項目，且必須為三碼英文字母", None)
    currency = currency_raw.strip().upper()

    # 4. 必填匯率 fx_rate_to_twd (大於 0)
    fx_rate_raw = payload.get("fx_rate_to_twd")
    if fx_rate_raw is None:
        return api_response(400, "折合台幣匯率為必填項目", None)
    try:
        fx_rate_to_twd = Decimal(str(fx_rate_raw))
    except (ValueError, TypeError, ArithmeticError):
        return api_response(400, "折合台幣匯率必須為有效數值", None)
    if fx_rate_to_twd <= 0:
        return api_response(400, "折合台幣匯率必須大於 0", None)

    # 5. 必填轉出帳戶與轉入帳戶
    from_account_id = payload.get("from_account_id")
    to_account_id = payload.get("to_account_id")
    if from_account_id is None or to_account_id is None:
        return api_response(400, "轉出帳戶與轉入帳戶為必填項目", None)
    if not isinstance(from_account_id, int) or isinstance(from_account_id, bool):
        return api_response(400, "轉出帳戶代碼格式不正確", None)
    if not isinstance(to_account_id, int) or isinstance(to_account_id, bool):
        return api_response(400, "轉入帳戶代碼格式不正確", None)

    # 轉出轉入相同
    if from_account_id == to_account_id:
        return api_response(400, "轉出帳戶與轉入帳戶不可相同", None)

    # 指向不存在的帳戶
    from_account = db.session.get(Account, from_account_id)
    if not from_account:
        return api_response(400, "轉出帳戶不存在", None)
    to_account = db.session.get(Account, to_account_id)
    if not to_account:
        return api_response(400, "轉入帳戶不存在", None)

    # 6. 選填備註 note (送 null 與省略相同)
    note_raw = payload.get("note")
    note = str(note_raw).strip() if note_raw is not None else None

    # 客戶端不送主鍵與 created_at，送了也不採用
    transfer = Transfer(
        transferred_on=transferred_on,
        amount=amount,
        currency=currency,
        fx_rate_to_twd=fx_rate_to_twd,
        from_account_id=from_account_id,
        to_account_id=to_account_id,
        note=note,
    )
    db.session.add(transfer)
    db.session.commit()

    return api_response(201, "移轉記錄新增成功", transfer.to_dict())


@transfers_bp.get("/<int:transfer_id>")
def get_transfer(transfer_id: int):
    """取得單一移轉記錄。若無該列回傳 404。"""
    transfer = db.session.get(Transfer, transfer_id)
    if not transfer:
        return api_response(404, "找不到指定的移轉記錄", None)
    return api_response(200, "取得移轉記錄成功", transfer.to_dict())
