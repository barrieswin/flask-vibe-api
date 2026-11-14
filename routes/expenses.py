"""花費相關 API 路由。"""

from datetime import date, datetime, timezone
from decimal import Decimal

from flask import Blueprint, request

from extensions import db
from models import Account, Expense, ExpenseCategory, Invoice
from utils import api_response

expenses_bp = Blueprint("expenses", __name__, url_prefix="/api/expenses")


@expenses_bp.get("")
def list_expenses():
    """取得花費記錄清單。

    可接受查詢參數 account_id、category_id、invoice_id、date_from、date_to。
    參數以參數化查詢綁定，值與語句分開送，不可拼進 SQL 字串。若無資料回傳 200 與空清單。
    """
    stmt = db.select(Expense)

    # 1. 帳戶過濾 account_id
    account_id_param = request.args.get("account_id")
    if account_id_param is not None and account_id_param.strip():
        try:
            account_id = int(account_id_param.strip())
        except ValueError:
            return api_response(400, "帳戶代碼格式不正確", None)
        stmt = stmt.where(Expense.account_id == account_id)

    # 2. 分類過濾 category_id
    category_id_param = request.args.get("category_id")
    if category_id_param is not None and category_id_param.strip():
        try:
            category_id = int(category_id_param.strip())
        except ValueError:
            return api_response(400, "分類代碼格式不正確", None)
        stmt = stmt.where(Expense.category_id == category_id)

    # 3. 發票過濾 invoice_id
    invoice_id_param = request.args.get("invoice_id")
    if invoice_id_param is not None and invoice_id_param.strip():
        try:
            invoice_id = int(invoice_id_param.strip())
        except ValueError:
            return api_response(400, "發票代碼格式不正確", None)
        stmt = stmt.where(Expense.invoice_id == invoice_id)

    # 4. 起始日期 date_from
    date_from_param = request.args.get("date_from")
    if date_from_param is not None and date_from_param.strip():
        try:
            date_from = date.fromisoformat(date_from_param.strip())
        except (ValueError, TypeError):
            return api_response(400, "起始日期格式不正確，請使用 YYYY-MM-DD 格式", None)
        stmt = stmt.where(Expense.spent_on >= date_from)

    # 5. 結束日期 date_to
    date_to_param = request.args.get("date_to")
    if date_to_param is not None and date_to_param.strip():
        try:
            date_to = date.fromisoformat(date_to_param.strip())
        except (ValueError, TypeError):
            return api_response(400, "結束日期格式不正確，請使用 YYYY-MM-DD 格式", None)
        stmt = stmt.where(Expense.spent_on <= date_to)

    stmt = stmt.order_by(Expense.spent_on.desc(), Expense.id.desc())
    expenses = db.session.scalars(stmt).all()
    return api_response(200, "取得花費清單成功", [exp.to_dict() for exp in expenses])


@expenses_bp.post("")
def create_expense():
    """新增花費記錄。

    必填消費日、金額、幣別、匯率、分類、帳戶。
    商家與備註至少一個有內容。
    merchant、note、settled_on、invoice_id 送 JSON 的 null，與省略該欄位相同。
    花費合計與發票總額不同時，仍接受寫入。
    成功回傳 201 與新增的那一列。
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_response(400, "請提供合法的 JSON 物件格式", None)

    # 1. 必填消費日 spent_on
    spent_on_raw = payload.get("spent_on")
    if spent_on_raw is None or not str(spent_on_raw).strip():
        return api_response(400, "消費日期為必填項目", None)
    try:
        spent_on = date.fromisoformat(str(spent_on_raw).strip())
    except (ValueError, TypeError):
        return api_response(400, "消費日期格式不正確，請使用 YYYY-MM-DD 格式", None)

    # 2. 選填結算日 settled_on (送 null 與省略相同)
    settled_on_raw = payload.get("settled_on")
    settled_on = None
    if settled_on_raw is not None and str(settled_on_raw).strip():
        try:
            settled_on = date.fromisoformat(str(settled_on_raw).strip())
        except (ValueError, TypeError):
            return api_response(400, "結算日期格式不正確，請使用 YYYY-MM-DD 格式", None)

    # 3. 必填金額 amount (大於 0)
    amount_raw = payload.get("amount")
    if amount_raw is None:
        return api_response(400, "花費金額為必填項目", None)
    try:
        amount = Decimal(str(amount_raw))
    except (ValueError, TypeError, ArithmeticError):
        return api_response(400, "花費金額必須為有效數值", None)
    if amount <= 0:
        return api_response(400, "花費金額必須大於 0", None)

    # 4. 必填幣別 currency (三碼)
    currency_raw = payload.get("currency")
    if (
        currency_raw is None
        or not isinstance(currency_raw, str)
        or len(currency_raw.strip()) != 3
    ):
        return api_response(400, "幣別代碼為必填項目，且必須為三碼英文字母", None)
    currency = currency_raw.strip().upper()

    # 5. 必填匯率 fx_rate_to_twd (大於 0)
    fx_rate_raw = payload.get("fx_rate_to_twd")
    if fx_rate_raw is None:
        return api_response(400, "折合台幣匯率為必填項目", None)
    try:
        fx_rate_to_twd = Decimal(str(fx_rate_raw))
    except (ValueError, TypeError, ArithmeticError):
        return api_response(400, "折合台幣匯率必須為有效數值", None)
    if fx_rate_to_twd <= 0:
        return api_response(400, "折合台幣匯率必須大於 0", None)

    # 6. 必填分類 category_id（必須存在）
    category_id = payload.get("category_id")
    if (
        category_id is None
        or not isinstance(category_id, int)
        or isinstance(category_id, bool)
    ):
        return api_response(400, "花費分類為必填項目", None)
    category = db.session.get(ExpenseCategory, category_id)
    if not category:
        return api_response(400, "指定的花費分類不存在", None)

    # 7. 必填帳戶 account_id（必須存在）
    account_id = payload.get("account_id")
    if (
        account_id is None
        or not isinstance(account_id, int)
        or isinstance(account_id, bool)
    ):
        return api_response(400, "扣款帳戶為必填項目", None)
    account = db.session.get(Account, account_id)
    if not account:
        return api_response(400, "指定的帳戶不存在", None)

    # 8. merchant 與 note：送 null 與省略該欄位相同；兩者至少一個有內容
    merchant_raw = payload.get("merchant")
    merchant = None
    if merchant_raw is not None:
        if isinstance(merchant_raw, str):
            merchant = merchant_raw.strip() or None
        else:
            return api_response(400, "商家格式不正確", None)

    note_raw = payload.get("note")
    note = None
    if note_raw is not None:
        if isinstance(note_raw, str):
            note = note_raw.strip() or None
        else:
            return api_response(400, "備註格式不正確", None)

    if not merchant and not note:
        return api_response(400, "商家與備註不可同時為空，至少需填寫一項", None)

    # 9. 選填 invoice_id（送 null 與省略相同；若提供必須存在，可多對一）
    invoice_id = payload.get("invoice_id")
    if invoice_id is not None:
        if not isinstance(invoice_id, int) or isinstance(invoice_id, bool):
            return api_response(400, "發票代碼格式不正確", None)
        invoice = db.session.get(Invoice, invoice_id)
        if not invoice:
            return api_response(400, "指定的發票不存在", None)

    # 客戶端不送主鍵與 created_at
    expense = Expense(
        spent_on=spent_on,
        settled_on=settled_on,
        amount=amount,
        currency=currency,
        fx_rate_to_twd=fx_rate_to_twd,
        category_id=category_id,
        account_id=account_id,
        merchant=merchant,
        note=note,
        invoice_id=invoice_id,
    )
    db.session.add(expense)
    db.session.commit()

    return api_response(201, "花費記錄新增成功", expense.to_dict())


@expenses_bp.get("/<int:expense_id>")
def get_expense(expense_id: int):
    """取得單一花費記錄。若無該列回傳 404。"""
    expense = db.session.get(Expense, expense_id)
    if not expense:
        return api_response(404, "找不到指定的花費記錄", None)
    return api_response(200, "取得花費記錄成功", expense.to_dict())


@expenses_bp.patch("/<int:expense_id>")
def update_expense(expense_id: int):
    """修改花費記錄。

    PATCH 不可改主鍵。
    更新時寫入 updated_at。
    merchant、note、settled_on、invoice_id 送 JSON 的 null，與省略該欄位相同。
    """
    expense = db.session.get(Expense, expense_id)
    if not expense:
        return api_response(404, "找不到指定的花費記錄", None)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_response(400, "請提供合法的 JSON 物件格式", None)

    # 不可改主鍵
    if "id" in payload and payload["id"] != expense.id:
        return api_response(400, "不可修改主鍵", None)

    # 1. 修改消費日期 spent_on
    if "spent_on" in payload:
        spent_on_raw = payload.get("spent_on")
        if spent_on_raw is None or not str(spent_on_raw).strip():
            return api_response(400, "消費日期不可為空", None)
        try:
            expense.spent_on = date.fromisoformat(str(spent_on_raw).strip())
        except (ValueError, TypeError):
            return api_response(400, "消費日期格式不正確，請使用 YYYY-MM-DD 格式", None)

    # 2. 修改結算日期 settled_on（送 null 代表清除為 None）
    if "settled_on" in payload:
        settled_on_raw = payload.get("settled_on")
        if settled_on_raw is None or not str(settled_on_raw).strip():
            expense.settled_on = None
        else:
            try:
                expense.settled_on = date.fromisoformat(str(settled_on_raw).strip())
            except (ValueError, TypeError):
                return api_response(400, "結算日期格式不正確，請使用 YYYY-MM-DD 格式", None)

    # 3. 修改金額 amount
    if "amount" in payload:
        amount_raw = payload.get("amount")
        if amount_raw is None:
            return api_response(400, "花費金額不可為空", None)
        try:
            amount = Decimal(str(amount_raw))
        except (ValueError, TypeError, ArithmeticError):
            return api_response(400, "花費金額必須為有效數值", None)
        if amount <= 0:
            return api_response(400, "花費金額必須大於 0", None)
        expense.amount = amount

    # 4. 修改幣別 currency
    if "currency" in payload:
        currency_raw = payload.get("currency")
        if (
            currency_raw is None
            or not isinstance(currency_raw, str)
            or len(currency_raw.strip()) != 3
        ):
            return api_response(400, "幣別代碼必須為三碼英文字母", None)
        expense.currency = currency_raw.strip().upper()

    # 5. 修改匯率 fx_rate_to_twd
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
        expense.fx_rate_to_twd = fx_rate

    # 6. 修改分類 category_id
    if "category_id" in payload:
        category_id = payload.get("category_id")
        if (
            category_id is None
            or not isinstance(category_id, int)
            or isinstance(category_id, bool)
        ):
            return api_response(400, "花費分類格式不正確", None)
        category = db.session.get(ExpenseCategory, category_id)
        if not category:
            return api_response(400, "指定的花費分類不存在", None)
        expense.category_id = category_id

    # 7. 修改帳戶 account_id
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
        expense.account_id = account_id

    # 8. 修改 invoice_id（送 null 代表清除為 None；若為整數則驗證發票是否存在）
    if "invoice_id" in payload:
        invoice_id = payload.get("invoice_id")
        if invoice_id is None:
            expense.invoice_id = None
        else:
            if not isinstance(invoice_id, int) or isinstance(invoice_id, bool):
                return api_response(400, "發票代碼格式不正確", None)
            invoice = db.session.get(Invoice, invoice_id)
            if not invoice:
                return api_response(400, "指定的發票不存在", None)
            expense.invoice_id = invoice_id

    # 9. 修改 merchant 與 note
    # 若兩者都在 payload 且皆為 null / 空，回傳 400
    merchant_in_payload = "merchant" in payload
    note_in_payload = "note" in payload

    if (
        merchant_in_payload
        and payload["merchant"] is None
        and note_in_payload
        and payload["note"] is None
    ):
        return api_response(400, "商家與備註不可同時為空，至少需填寫一項", None)

    new_merchant = expense.merchant
    if merchant_in_payload:
        merchant_val = payload["merchant"]
        if merchant_val is not None:
            if isinstance(merchant_val, str):
                new_merchant = merchant_val.strip() or None
            else:
                return api_response(400, "商家格式不正確", None)

    new_note = expense.note
    if note_in_payload:
        note_val = payload["note"]
        if note_val is not None:
            if isinstance(note_val, str):
                new_note = note_val.strip() or None
            else:
                return api_response(400, "備註格式不正確", None)

    if not new_merchant and not new_note:
        return api_response(400, "商家與備註不可同時為空，至少需填寫一項", None)

    expense.merchant = new_merchant
    expense.note = new_note

    # 更新時寫入 updated_at
    expense.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return api_response(200, "花費記錄更新成功", expense.to_dict())
