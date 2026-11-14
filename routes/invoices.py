"""統一發票相關 API 路由。"""

import re
from datetime import date, datetime, timezone
from decimal import Decimal

from flask import Blueprint, request

from extensions import db
from models import Account, DrawPeriod, DrawPrize, Income, IncomeCategory, Invoice, InvoiceItem
from utils import api_response, get_period_date_range, get_period_key

invoices_bp = Blueprint("invoices", __name__, url_prefix="/api/invoices")

ALLOWED_KINDS = {"paper", "electronic"}
INVOICE_NUMBER_REGEX = re.compile(r"^[A-Z]{2}[0-9]{8}$")


def _find_matching_prizes(inv_number: str, prizes: list[DrawPrize]) -> list[DrawPrize]:
    """比對發票 8 碼數字與獎項列表，回傳所有中獎獎項。"""
    inv_digits = inv_number[2:]
    matched = []
    for prize in prizes:
        if prize.tier in ("special", "grand", "first"):
            if inv_digits == prize.matching_number:
                matched.append(prize)
        elif prize.tier == "second":
            if inv_digits.endswith(prize.matching_number[-7:]):
                matched.append(prize)
        elif prize.tier == "third":
            if inv_digits.endswith(prize.matching_number[-6:]):
                matched.append(prize)
        elif prize.tier == "fourth":
            if inv_digits.endswith(prize.matching_number[-5:]):
                matched.append(prize)
        elif prize.tier == "fifth":
            if inv_digits.endswith(prize.matching_number[-4:]):
                matched.append(prize)
        elif prize.tier in ("sixth", "extra_sixth"):
            if inv_digits.endswith(prize.matching_number[-3:]):
                matched.append(prize)
    return matched


@invoices_bp.post("")
def create_invoice():
    """新增發票。

    必填號碼、開立日、金額、種類。
    幣別未送時用 TWD，匯率未送且幣別為 TWD 時用 1。
    成功回傳 201 與寫入後的那一列。
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_response(400, "請提供合法的 JSON 物件格式", None)

    # 1. 必填發票號碼 number
    number_raw = payload.get("number")
    if not isinstance(number_raw, str) or not number_raw.strip():
        return api_response(400, "發票號碼為必填項目且不可為空", None)
    number = number_raw.strip()
    if not INVOICE_NUMBER_REGEX.match(number):
        return api_response(
            400, "發票號碼格式不符，必須為兩碼大寫英文加八碼數字", None
        )

    # 檢查號碼重複
    existing = db.session.scalar(db.select(Invoice).filter_by(number=number))
    if existing:
        return api_response(400, "發票號碼已存在，不可重複", None)

    # 2. 必填開立日期 issued_on
    issued_on_raw = payload.get("issued_on")
    if issued_on_raw is None or not str(issued_on_raw).strip():
        return api_response(400, "開立日期為必填項目", None)
    try:
        issued_on = date.fromisoformat(str(issued_on_raw).strip())
    except (ValueError, TypeError):
        return api_response(400, "開立日期格式不正確，請使用 YYYY-MM-DD 格式", None)

    # 3. 必填金額 amount (大於 0)
    amount_raw = payload.get("amount")
    if amount_raw is None:
        return api_response(400, "發票金額為必填項目", None)
    try:
        amount = Decimal(str(amount_raw))
    except (ValueError, TypeError, ArithmeticError):
        return api_response(400, "發票金額必須為有效數值", None)
    if amount <= 0:
        return api_response(400, "發票金額必須大於 0", None)

    # 4. 必填種類 kind (paper 或 electronic)
    kind_raw = payload.get("kind")
    if not isinstance(kind_raw, str) or kind_raw.strip() not in ALLOWED_KINDS:
        return api_response(
            400, "發票種類不在允許清單中，只允許 paper 或 electronic", None
        )
    kind = kind_raw.strip()

    # 5. 幣別 currency (未送用 TWD)
    currency_raw = payload.get("currency")
    if currency_raw is None or not str(currency_raw).strip():
        currency = "TWD"
    else:
        if not isinstance(currency_raw, str) or len(currency_raw.strip()) != 3:
            return api_response(400, "幣別代碼必須為三碼英文字母", None)
        currency = currency_raw.strip().upper()

    # 6. 匯率 fx_rate_to_twd (未送且幣別為 TWD 時用 1)
    fx_rate_raw = payload.get("fx_rate_to_twd")
    if fx_rate_raw is None or not str(fx_rate_raw).strip():
        if currency == "TWD":
            fx_rate_to_twd = Decimal("1.000000")
        else:
            return api_response(400, "外幣發票必須填寫折合台幣匯率", None)
    else:
        try:
            fx_rate_to_twd = Decimal(str(fx_rate_raw))
        except (ValueError, TypeError, ArithmeticError):
            return api_response(400, "折合台幣匯率必須為有效數值", None)
        if fx_rate_to_twd <= 0:
            return api_response(400, "折合台幣匯率必須大於 0", None)

    # 7. 可選隨機碼 random_code (送 null 與省略相同)
    random_code_raw = payload.get("random_code")
    random_code = None
    if random_code_raw is not None and str(random_code_raw).strip():
        code_str = str(random_code_raw).strip()
        if not re.match(r"^\d{4}$", code_str):
            return api_response(400, "隨機碼必須為四碼數字", None)
        random_code = code_str

    # 8. 可選賣方名稱與統編 (送 null 與省略相同)
    seller_name_raw = payload.get("seller_name")
    seller_name = (
        seller_name_raw.strip()
        if isinstance(seller_name_raw, str) and seller_name_raw.strip()
        else None
    )

    seller_ban_raw = payload.get("seller_ban")
    seller_ban = (
        seller_ban_raw.strip()
        if isinstance(seller_ban_raw, str) and seller_ban_raw.strip()
        else None
    )

    invoice = Invoice(
        number=number,
        issued_on=issued_on,
        amount=amount,
        kind=kind,
        currency=currency,
        fx_rate_to_twd=fx_rate_to_twd,
        random_code=random_code,
        seller_name=seller_name,
        seller_ban=seller_ban,
        prize_status="unchecked",
    )
    db.session.add(invoice)
    db.session.commit()

    res_data = invoice.to_dict()
    res_data["period_key"] = get_period_key(invoice.issued_on)
    return api_response(201, "發票新增成功", res_data)


@invoices_bp.get("")
def list_invoices():
    """取得發票清單。可依 period_key、prize_status 篩選。"""
    stmt = db.select(Invoice)

    period_key = request.args.get("period_key")
    if period_key is not None and period_key.strip():
        start_date, next_start = get_period_date_range(period_key.strip())
        if not start_date or not next_start:
            return api_response(
                400, "期別格式不符，格式應為 YYYY-MM（月份為 01、03、05、07、09、11）", None
            )
        stmt = stmt.where(
            Invoice.issued_on >= start_date, Invoice.issued_on < next_start
        )

    prize_status = request.args.get("prize_status")
    if prize_status is not None and prize_status.strip():
        stmt = stmt.where(Invoice.prize_status == prize_status.strip())

    stmt = stmt.order_by(Invoice.issued_on.desc(), Invoice.id.desc())
    invoices = db.session.scalars(stmt).all()

    items = []
    for inv in invoices:
        d = inv.to_dict()
        d["period_key"] = get_period_key(inv.issued_on)
        items.append(d)

    return api_response(200, "取得發票清單成功", items)


@invoices_bp.get("/<int:invoice_id>")
def get_invoice(invoice_id: int):
    """取得單一發票，並在 data 帶上品項清單與已掛上的花費 id 清單。"""
    invoice = db.session.get(Invoice, invoice_id)
    if not invoice:
        return api_response(404, "找不到指定的發票", None)

    data = invoice.to_dict()
    data["period_key"] = get_period_key(invoice.issued_on)
    data["items"] = [item.to_dict() for item in invoice.items]
    data["expense_ids"] = [exp.id for exp in invoice.expenses]

    return api_response(200, "取得發票成功", data)


@invoices_bp.patch("/<int:invoice_id>")
def update_invoice(invoice_id: int):
    """修改發票。可改賣方、隨機碼；可把 prize_status 改成 void。不可改號碼與主鍵。"""
    invoice = db.session.get(Invoice, invoice_id)
    if not invoice:
        return api_response(404, "找不到指定的發票", None)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_response(400, "請提供合法的 JSON 物件格式", None)

    # 不可改主鍵
    if "id" in payload and payload["id"] != invoice.id:
        return api_response(400, "不可修改主鍵", None)

    # 不可改發票號碼
    if "number" in payload and payload["number"] != invoice.number:
        return api_response(400, "不可修改發票號碼", None)

    # 修改賣方名稱
    if "seller_name" in payload:
        seller_name_val = payload["seller_name"]
        if seller_name_val is None:
            invoice.seller_name = None
        elif isinstance(seller_name_val, str):
            invoice.seller_name = seller_name_val.strip() or None
        else:
            return api_response(400, "賣方名稱格式不正確", None)

    # 修改賣方統編
    if "seller_ban" in payload:
        seller_ban_val = payload["seller_ban"]
        if seller_ban_val is None:
            invoice.seller_ban = None
        elif isinstance(seller_ban_val, str):
            invoice.seller_ban = seller_ban_val.strip() or None
        else:
            return api_response(400, "賣方統一編號格式不正確", None)

    # 修改隨機碼
    if "random_code" in payload:
        random_code_val = payload["random_code"]
        if random_code_val is None:
            invoice.random_code = None
        else:
            code_str = str(random_code_val).strip()
            if not re.match(r"^\d{4}$", code_str):
                return api_response(400, "隨機碼必須為四碼數字", None)
            invoice.random_code = code_str

    # 修改 prize_status（僅允許改為 void）
    if "prize_status" in payload:
        status_val = payload["prize_status"]
        if status_val == "void":
            invoice.prize_status = "void"
        elif status_val == invoice.prize_status:
            pass
        else:
            return api_response(400, "對獎狀態僅允許修改為 void 作廢", None)

    invoice.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    res_data = invoice.to_dict()
    res_data["period_key"] = get_period_key(invoice.issued_on)
    return api_response(200, "發票更新成功", res_data)


@invoices_bp.post("/<int:invoice_id>/items")
def create_invoice_item(invoice_id: int):
    """新增發票品項。必填名稱、數量、單價、小計。"""
    invoice = db.session.get(Invoice, invoice_id)
    if not invoice:
        return api_response(404, "找不到指定的發票", None)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_response(400, "請提供合法的 JSON 物件格式", None)

    # 1. 必填品項名稱 name
    name_raw = payload.get("name")
    if not isinstance(name_raw, str) or not name_raw.strip():
        return api_response(400, "品項名稱為必填項目且不可為空", None)
    name = name_raw.strip()

    # 2. 必填數量 quantity (> 0)
    quantity_raw = payload.get("quantity")
    if quantity_raw is None:
        return api_response(400, "品項數量為必填項目", None)
    try:
        quantity = Decimal(str(quantity_raw))
    except (ValueError, TypeError, ArithmeticError):
        return api_response(400, "品項數量必須為有效數值", None)
    if quantity <= 0:
        return api_response(400, "品項數量必須大於 0", None)

    # 3. 必填單價 unit_price (> 0)
    unit_price_raw = payload.get("unit_price")
    if unit_price_raw is None:
        return api_response(400, "品項單價為必填項目", None)
    try:
        unit_price = Decimal(str(unit_price_raw))
    except (ValueError, TypeError, ArithmeticError):
        return api_response(400, "品項單價必須為有效數值", None)
    if unit_price <= 0:
        return api_response(400, "品項單價必須大於 0", None)

    # 4. 必填小計 line_amount (> 0)
    line_amount_raw = payload.get("line_amount")
    if line_amount_raw is None:
        return api_response(400, "品項小計為必填項目", None)
    try:
        line_amount = Decimal(str(line_amount_raw))
    except (ValueError, TypeError, ArithmeticError):
        return api_response(400, "品項小計必須為有效數值", None)
    if line_amount <= 0:
        return api_response(400, "品項小計必須大於 0", None)

    item = InvoiceItem(
        invoice_id=invoice.id,
        name=name,
        quantity=quantity,
        unit_price=unit_price,
        line_amount=line_amount,
    )
    db.session.add(item)
    db.session.commit()

    return api_response(201, "發票品項新增成功", item.to_dict())


@invoices_bp.get("/<int:invoice_id>/items")
def list_invoice_items(invoice_id: int):
    """取得發票品項清單，空的回 200。"""
    invoice = db.session.get(Invoice, invoice_id)
    if not invoice:
        return api_response(404, "找不到指定的發票", None)

    items = db.session.scalars(
        db.select(InvoiceItem)
        .filter_by(invoice_id=invoice.id)
        .order_by(InvoiceItem.id.asc())
    ).all()
    return api_response(
        200, "取得發票品項清單成功", [item.to_dict() for item in items]
    )


@invoices_bp.post("/<int:invoice_id>/prize-income")
def claim_prize_income(invoice_id: int):
    """將已中獎發票兌獎入帳。

    僅 prize_status 為 won 且尚未有入帳時可呼叫。
    同一筆交易裡新增一筆 incomes（金額為對到的獎金、匯率沿用發票、invoice_id 指向這張發票），並把發票改為 claimed。
    請求必填 category_id 與 account_id。
    """
    invoice = db.session.get(Invoice, invoice_id)
    if not invoice:
        return api_response(404, "找不到指定的發票", None)

    if invoice.prize_status != "won":
        return api_response(400, "發票狀態非中獎狀態（won），無法建立中獎入帳", None)

    # 檢查是否已存在對應入帳
    existing_income = db.session.scalar(
        db.select(Income).filter_by(invoice_id=invoice.id)
    )
    if existing_income:
        return api_response(400, "此發票已建立過中獎入帳，不可重複呼叫", None)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_response(400, "請提供合法的 JSON 物件格式", None)

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

    # 尋找該發票期別與中獎獎金
    period_key = get_period_key(invoice.issued_on)
    period = db.session.scalar(
        db.select(DrawPeriod).filter_by(period_key=period_key)
    )
    if not period:
        return api_response(400, "找不到該發票所屬期別的開獎記錄", None)

    prizes = db.session.scalars(
        db.select(DrawPrize).filter_by(draw_period_id=period.id)
    ).all()
    matched = _find_matching_prizes(invoice.number, prizes)
    if not matched:
        return api_response(400, "此發票未對中該期之有效獎項", None)

    # 取中獎金額最高之獎項
    winning_prize = max(matched, key=lambda p: p.amount)
    prize_amount = winning_prize.amount

    # 同一筆交易內建立入帳並改狀態為 claimed
    income = Income(
        received_on=datetime.now(timezone.utc).date(),
        amount=prize_amount,
        currency=invoice.currency,
        fx_rate_to_twd=invoice.fx_rate_to_twd,
        category_id=category_id,
        account_id=account_id,
        source=f"統一發票中獎",
        note=f"發票號碼 {invoice.number} 中獎獎金",
        invoice_id=invoice.id,
    )
    invoice.prize_status = "claimed"
    invoice.updated_at = datetime.now(timezone.utc)

    db.session.add(income)
    db.session.commit()

    return api_response(201, "中獎發票已成功建立入帳", income.to_dict())
