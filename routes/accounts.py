"""帳戶相關 API 路由。"""

from datetime import datetime, timezone
from decimal import Decimal

from flask import Blueprint, request

from extensions import db
from models import Account, Expense, Income, Transfer
from utils import api_response

accounts_bp = Blueprint("accounts", __name__, url_prefix="/api/accounts")

ALLOWED_KINDS = {"cash", "bank", "credit_card", "broker"}


@accounts_bp.get("")
def list_accounts():
    """取得帳戶清單。若無資料回傳 200 與空清單。"""
    accounts = db.session.scalars(db.select(Account).order_by(Account.id.asc())).all()
    return api_response(200, "取得帳戶清單成功", [acc.to_dict() for acc in accounts])


@accounts_bp.post("")
def create_account():
    """新增帳戶。必填 name、kind。成功回傳 201。"""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_response(400, "請提供合法的 JSON 物件格式", None)

    # 1. 必填 name
    name_raw = payload.get("name")
    if not isinstance(name_raw, str) or not name_raw.strip():
        return api_response(400, "帳戶名稱為必填項目且不可為空", None)
    name = name_raw.strip()

    # 檢查名稱重複
    existing = db.session.scalar(db.select(Account).filter_by(name=name))
    if existing:
        return api_response(400, "帳戶名稱已存在，不可重複", None)

    # 2. 必填 kind
    kind_raw = payload.get("kind")
    if not isinstance(kind_raw, str) or kind_raw.strip() not in ALLOWED_KINDS:
        return api_response(
            400,
            "帳戶種類不在允許清單中，只允許 cash、bank、credit_card、broker",
            None,
        )
    kind = kind_raw.strip()

    # 3. 幣別 currency (可空/省略，預設 TWD)
    currency_raw = payload.get("currency")
    if currency_raw is None:
        currency = "TWD"
    else:
        if not isinstance(currency_raw, str) or len(currency_raw.strip()) != 3:
            return api_response(400, "幣別代碼必須為三碼英文字母", None)
        currency = currency_raw.strip().upper()

    # 4. 開帳餘額 opening_balance (可空/省略，預設 0)
    opening_balance_raw = payload.get("opening_balance")
    if opening_balance_raw is None:
        opening_balance = Decimal("0.0000")
    else:
        try:
            opening_balance = Decimal(str(opening_balance_raw))
        except (ValueError, TypeError, ArithmeticError):
            return api_response(400, "開帳餘額必須為有效數值", None)

    # 5. 結帳日 statement_day (可空，有值時介於 1 到 31)
    statement_day = payload.get("statement_day")
    if statement_day is not None:
        if not isinstance(statement_day, int) or isinstance(statement_day, bool) or not (1 <= statement_day <= 31):
            return api_response(400, "結帳日必須介於 1 到 31 之間", None)

    # 6. 繳款日 payment_day (可空，有值時介於 1 到 31)
    payment_day = payload.get("payment_day")
    if payment_day is not None:
        if not isinstance(payment_day, int) or isinstance(payment_day, bool) or not (1 <= payment_day <= 31):
            return api_response(400, "繳款日必須介於 1 到 31 之間", None)

    # 客戶端不送主鍵與 created_at，送了也不採用
    account = Account(
        name=name,
        kind=kind,
        currency=currency,
        opening_balance=opening_balance,
        statement_day=statement_day,
        payment_day=payment_day,
    )
    db.session.add(account)
    db.session.commit()

    return api_response(201, "帳戶新增成功", account.to_dict())


@accounts_bp.get("/<int:account_id>")
def get_account(account_id: int):
    """取得單一帳戶。若無該列回傳 404。"""
    account = db.session.get(Account, account_id)
    if not account:
        return api_response(404, "找不到指定的帳戶", None)
    return api_response(200, "取得帳戶成功", account.to_dict())


@accounts_bp.patch("/<int:account_id>")
def update_account(account_id: int):
    """修改帳戶資訊。可改名稱、結帳日、繳款日。改 updated_at。不可改主鍵。"""
    account = db.session.get(Account, account_id)
    if not account:
        return api_response(404, "找不到指定的帳戶", None)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_response(400, "請提供合法的 JSON 物件格式", None)

    # 修改名稱
    if "name" in payload:
        name_raw = payload.get("name")
        if not isinstance(name_raw, str) or not name_raw.strip():
            return api_response(400, "帳戶名稱不可為空", None)
        name = name_raw.strip()
        if name != account.name:
            existing = db.session.scalar(
                db.select(Account).filter(Account.name == name, Account.id != account.id)
            )
            if existing:
                return api_response(400, "帳戶名稱已存在，不可重複", None)
            account.name = name

    # 修改結帳日（送 null 代表清除）
    if "statement_day" in payload:
        statement_day = payload.get("statement_day")
        if statement_day is not None:
            if not isinstance(statement_day, int) or isinstance(statement_day, bool) or not (1 <= statement_day <= 31):
                return api_response(400, "結帳日必須介於 1 到 31 之間", None)
            account.statement_day = statement_day
        else:
            account.statement_day = None

    # 修改繳款日（送 null 代表清除）
    if "payment_day" in payload:
        payment_day = payload.get("payment_day")
        if payment_day is not None:
            if not isinstance(payment_day, int) or isinstance(payment_day, bool) or not (1 <= payment_day <= 31):
                return api_response(400, "繳款日必須介於 1 到 31 之間", None)
            account.payment_day = payment_day
        else:
            account.payment_day = None

    # 改 updated_at；不可改主鍵（忽略 payload 中可能帶入的 id 與 created_at）
    account.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return api_response(200, "帳戶更新成功", account.to_dict())


@accounts_bp.get("/<int:account_id>/balance")
def get_account_balance(account_id: int):
    """計算並取得帳戶餘額。此端點不寫入。

    餘額 = opening_balance，加上轉入、減去轉出、加上入帳、減去花費。金額先乘上該列的 fx_rate_to_twd。
    回傳的 data 含原幣別餘額與台幣餘額。
    """
    account = db.session.get(Account, account_id)
    if not account:
        return api_response(404, "找不到指定的帳戶", None)

    transfers_in = db.session.scalars(
        db.select(Transfer).filter_by(to_account_id=account.id)
    ).all()
    transfers_out = db.session.scalars(
        db.select(Transfer).filter_by(from_account_id=account.id)
    ).all()
    incomes = db.session.scalars(
        db.select(Income).filter_by(account_id=account.id)
    ).all()
    expenses = db.session.scalars(
        db.select(Expense).filter_by(account_id=account.id)
    ).all()

    opening_balance = account.opening_balance if account.opening_balance is not None else Decimal("0")

    # 原幣別餘額
    in_raw = sum((t.amount for t in transfers_in), Decimal("0"))
    out_raw = sum((t.amount for t in transfers_out), Decimal("0"))
    income_raw = sum((inc.amount for inc in incomes), Decimal("0"))
    expense_raw = sum((exp.amount for exp in expenses), Decimal("0"))
    raw_balance = opening_balance + in_raw - out_raw + income_raw - expense_raw

    # 台幣餘額（金額先乘上該列的 fx_rate_to_twd）
    in_twd = sum((t.amount * t.fx_rate_to_twd for t in transfers_in), Decimal("0"))
    out_twd = sum((t.amount * t.fx_rate_to_twd for t in transfers_out), Decimal("0"))
    income_twd = sum((inc.amount * inc.fx_rate_to_twd for inc in incomes), Decimal("0"))
    expense_twd = sum((exp.amount * exp.fx_rate_to_twd for exp in expenses), Decimal("0"))
    balance_twd = opening_balance + in_twd - out_twd + income_twd - expense_twd

    data = {
        "account_id": account.id,
        "name": account.name,
        "currency": account.currency,
        "opening_balance": float(opening_balance),
        "balance": float(round(raw_balance, 4)),
        "balance_twd": float(round(balance_twd, 4)),
        "original_currency_balance": float(round(raw_balance, 4)),
        "twd_balance": float(round(balance_twd, 4)),
    }

    return api_response(200, "取得帳戶餘額成功", data)
