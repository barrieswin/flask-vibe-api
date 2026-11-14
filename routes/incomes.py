"""入帳相關 API 路由。"""

from datetime import date, datetime, timezone
from decimal import Decimal

from flask import Blueprint, request

from extensions import db
from models import Account, Income, IncomeCategory, Invoice
from utils import api_response

incomes_bp = Blueprint("incomes", __name__, url_prefix="/api/incomes")


@incomes_bp.get("")
def list_incomes():
    """取得入帳記錄清單。

    可接受查詢參數 account_id、category_id、date_from、date_to。
    參數以參數化查詢綁定，不可拼進 SQL 字串。若無資料回傳 200 與空清單。
    """
    stmt = db.select(Income)

    # 1. 帳戶過濾 account_id
    account_id_param = request.args.get("account_id")
    if account_id_param is not None and account_id_param.strip():
        try:
            account_id = int(account_id_param.strip())
        except ValueError:
            return api_response(400, "帳戶代碼格式不正確", None)
        stmt = stmt.where(Income.account_id == account_id)

    # 2. 分類過濾 category_id
    category_id_param = request.args.get("category_id")
    if category_id_param is not None and category_id_param.strip():
        try:
            category_id = int(category_id_param.strip())
        except ValueError:
            return api_response(400, "分類代碼格式不正確", None)
        stmt = stmt.where(Income.category_id == category_id)

    # 3. 起始日期 date_from
    date_from_param = request.args.get("date_from")
    if date_from_param is not None and date_from_param.strip():
        try:
            date_from = date.fromisoformat(date_from_param.strip())
        except (ValueError, TypeError):
            return api_response(400, "起始日期格式不正確，請使用 YYYY-MM-DD 格式", None)
        stmt = stmt.where(Income.received_on >= date_from)

    # 4. 結束日期 date_to
    date_to_param = request.args.get("date_to")
    if date_to_param is not None and date_to_param.strip():
        try:
            date_to = date.fromisoformat(date_to_param.strip())
        except (ValueError, TypeError):
            return api_response(400, "結束日期格式不正確，請使用 YYYY-MM-DD 格式", None)
        stmt = stmt.where(Income.received_on <= date_to)

    stmt = stmt.order_by(Income.received_on.desc(), Income.id.desc())
    incomes = db.session.scalars(stmt).all()
    return api_response(200, "取得入帳清單成功", [inc.to_dict() for inc in incomes])


@incomes_bp.post("")
def create_income():
    """新增入帳記錄。

    必填日期、金額、幣別、匯率、分類、帳戶。
    source 與 note 至少一個有內容。
    source 或 note 送 JSON 的 null，與省略該欄位相同。
    成功回傳 201 與新增的那一列。
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_response(400, "請提供合法的 JSON 物件格式", None)

    # 1. 必填日期 received_on
    received_on_raw = payload.get("received_on")
    if received_on_raw is None or not str(received_on_raw).strip():
        return api_response(400, "入帳日期為必填項目", None)
    try:
        received_on = date.fromisoformat(str(received_on_raw).strip())
    except (ValueError, TypeError):
        return api_response(400, "入帳日期格式不正確，請使用 YYYY-MM-DD 格式", None)

    # 2. 必填金額 amount (大於 0)
    amount_raw = payload.get("amount")
    if amount_raw is None:
        return api_response(400, "入帳金額為必填項目", None)
    try:
        amount = Decimal(str(amount_raw))
    except (ValueError, TypeError, ArithmeticError):
        return api_response(400, "入帳金額必須為有效數值", None)
    if amount <= 0:
        return api_response(400, "入帳金額必須大於 0", None)

    # 3. 必填幣別 currency (三碼)
    currency_raw = payload.get("currency")
    if (
        currency_raw is None
        or not isinstance(currency_raw, str)
        or len(currency_raw.strip()) != 3
    ):
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

    # 5. 必填分類 category_id（必須存在）
    category_id = payload.get("category_id")
    if (
        category_id is None
        or not isinstance(category_id, int)
        or isinstance(category_id, bool)
    ):
        return api_response(400, "入帳分類為必填項目", None)
    category = db.session.get(IncomeCategory, category_id)
    if not category:
        return api_response(400, "指定的入帳分類不存在", None)

    # 6. 必填帳戶 account_id（必須存在）
    account_id = payload.get("account_id")
    if (
        account_id is None
        or not isinstance(account_id, int)
        or isinstance(account_id, bool)
    ):
        return api_response(400, "入帳帳戶為必填項目", None)
    account = db.session.get(Account, account_id)
    if not account:
        return api_response(400, "指定的帳戶不存在", None)

    # 7. source 與 note：送 null 與省略該欄位相同；兩者至少一個有內容
    source_raw = payload.get("source")
    source = None
    if source_raw is not None:
        if isinstance(source_raw, str):
            source = source_raw.strip() or None
        else:
            return api_response(400, "來源格式不正確", None)

    note_raw = payload.get("note")
    note = None
    if note_raw is not None:
        if isinstance(note_raw, str):
            note = note_raw.strip() or None
        else:
            return api_response(400, "備註格式不正確", None)

    if not source and not note:
        return api_response(400, "來源與備註不可同時為空，至少需填寫一項", None)

    # 8. 可選 invoice_id（若提供必須存在且唯一）
    invoice_id = payload.get("invoice_id")
    if invoice_id is not None:
        if not isinstance(invoice_id, int) or isinstance(invoice_id, bool):
            return api_response(400, "發票代碼格式不正確", None)
        invoice = db.session.get(Invoice, invoice_id)
        if not invoice:
            return api_response(400, "指定的發票不存在", None)
        existing_income = db.session.scalar(
            db.select(Income).filter_by(invoice_id=invoice_id)
        )
        if existing_income:
            return api_response(400, "此發票已綁定其他入帳記錄", None)

    # 客戶端不送主鍵與 created_at
    income = Income(
        received_on=received_on,
        amount=amount,
        currency=currency,
        fx_rate_to_twd=fx_rate_to_twd,
        category_id=category_id,
        account_id=account_id,
        source=source,
        note=note,
        invoice_id=invoice_id,
    )
    db.session.add(income)
    db.session.commit()

    return api_response(201, "入帳記錄新增成功", income.to_dict())


@incomes_bp.get("/<int:income_id>")
def get_income(income_id: int):
    """取得單一入帳記錄。若無該列回傳 404。"""
    income = db.session.get(Income, income_id)
    if not income:
        return api_response(404, "找不到指定的入帳記錄", None)
    return api_response(200, "取得入帳記錄成功", income.to_dict())


@incomes_bp.patch("/<int:income_id>")
def update_income(income_id: int):
    """修改入帳記錄。

    PATCH 不可改主鍵與 invoice_id。
    更新時寫入 updated_at。
    source 或 note 送 JSON 的 null，與省略該欄位相同。
    """
    income = db.session.get(Income, income_id)
    if not income:
        return api_response(404, "找不到指定的入帳記錄", None)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_response(400, "請提供合法的 JSON 物件格式", None)

    # 不可改主鍵
    if "id" in payload and payload["id"] != income.id:
        return api_response(400, "不可修改主鍵", None)

    # PATCH 不可改 invoice_id
    if "invoice_id" in payload and payload["invoice_id"] != income.invoice_id:
        return api_response(400, "不可修改關聯發票", None)

    # 1. 修改入帳日期 received_on
    if "received_on" in payload:
        received_on_raw = payload.get("received_on")
        if received_on_raw is None or not str(received_on_raw).strip():
            return api_response(400, "入帳日期不可為空", None)
        try:
            income.received_on = date.fromisoformat(str(received_on_raw).strip())
        except (ValueError, TypeError):
            return api_response(400, "入帳日期格式不正確，請使用 YYYY-MM-DD 格式", None)

    # 2. 修改金額 amount
    if "amount" in payload:
        amount_raw = payload.get("amount")
        if amount_raw is None:
            return api_response(400, "入帳金額不可為空", None)
        try:
            amount = Decimal(str(amount_raw))
        except (ValueError, TypeError, ArithmeticError):
            return api_response(400, "入帳金額必須為有效數值", None)
        if amount <= 0:
            return api_response(400, "入帳金額必須大於 0", None)
        income.amount = amount

    # 3. 修改幣別 currency
    if "currency" in payload:
        currency_raw = payload.get("currency")
        if (
            currency_raw is None
            or not isinstance(currency_raw, str)
            or len(currency_raw.strip()) != 3
        ):
            return api_response(400, "幣別代碼必須為三碼英文字母", None)
        income.currency = currency_raw.strip().upper()

    # 4. 修改匯率 fx_rate_to_twd
    if "fx_rate_to_twd" in payload:
        fx_rate_raw = payload.get("fx_rate_to_twd")
        if fx_rate_raw is None:
            return api_response(400, "折合台幣匯率不可為空", None)
        try:
            fx_rate = Decimal(str(fx_rate_raw))
        except (ValueError, TypeError, ArithmeticError):
            return api_response(400, "折合台幣匯率必須為有效數值", None)
        if fx_rate <= 0:
            return api_response(400, "折合台幣匯率必須大於 0", None)
        income.fx_rate_to_twd = fx_rate

    # 5. 修改分類 category_id
    if "category_id" in payload:
        category_id = payload.get("category_id")
        if (
            category_id is None
            or not isinstance(category_id, int)
            or isinstance(category_id, bool)
        ):
            return api_response(400, "入帳分類格式不正確", None)
        category = db.session.get(IncomeCategory, category_id)
        if not category:
            return api_response(400, "指定的入帳分類不存在", None)
        income.category_id = category_id

    # 6. 修改帳戶 account_id
    if "account_id" in payload:
        account_id = payload.get("account_id")
        if (
            account_id is None
            or not isinstance(account_id, int)
            or isinstance(account_id, bool)
        ):
            return api_response(400, "帳戶代碼格式不正確", None)
        account = db.session.get(Account, account_id)
        if not account:
            return api_response(400, "指定的帳戶不存在", None)
        income.account_id = account_id

    # 7. 修改 source 與 note
    # 若兩者都在 payload 且皆為 null / 空，回傳 400
    source_in_payload = "source" in payload
    note_in_payload = "note" in payload

    if (
        source_in_payload
        and payload["source"] is None
        and note_in_payload
        and payload["note"] is None
    ):
        return api_response(400, "來源與備註不可同時為空，至少需填寫一項", None)

    new_source = income.source
    if source_in_payload:
        source_val = payload["source"]
        if source_val is not None:
            if isinstance(source_val, str):
                new_source = source_val.strip() or None
            else:
                return api_response(400, "來源格式不正確", None)

    new_note = income.note
    if note_in_payload:
        note_val = payload["note"]
        if note_val is not None:
            if isinstance(note_val, str):
                new_note = note_val.strip() or None
            else:
                return api_response(400, "備註格式不正確", None)

    if not new_source and not new_note:
        return api_response(400, "來源與備註不可同時為空，至少需填寫一項", None)

    income.source = new_source
    income.note = new_note

    # 更新時寫入 updated_at
    income.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return api_response(200, "入帳記錄更新成功", income.to_dict())
