"""投資交易相關 API 路由。"""

from datetime import date, datetime, timezone
from decimal import Decimal

from flask import Blueprint, request

from extensions import db
from models import Account, Income, IncomeCategory, Instrument, Trade
from routes.instruments import calculate_holding
from utils import api_response

trades_bp = Blueprint("trades", __name__, url_prefix="/api/trades")

ALLOWED_TRADE_TYPES = {
    "buy",
    "sell",
    "cash_dividend",
    "stock_dividend",
    "drip",
    "split",
    "merge",
    "capital_reduction",
}


@trades_bp.post("")
def create_trade():
    """新增投資交易。

    必填標的、帳戶、種類、日期、幣別、匯率。
    依種類要求數量、價格、比例或現金金額。
    sell 與 capital_reduction 若會使持有小於 0，回 400，不要寫入。
    post_income 為真且種類為 cash_dividend 或 capital_reduction 帶有 cash_amount 時，
    同一筆資料庫交易內新增 incomes。
    成功回傳 201 與寫入後的交易。
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_response(400, "請提供合法的 JSON 物件格式", None)

    # 1. 必填標的 instrument_id
    instrument_id = payload.get("instrument_id")
    if (
        instrument_id is None
        or not isinstance(instrument_id, int)
        or isinstance(instrument_id, bool)
    ):
        return api_response(400, "投資標的為必填項目", None)
    instrument = db.session.get(Instrument, instrument_id)
    if not instrument:
        return api_response(400, "指定的投資標的不存在", None)

    # 2. 必填帳戶 account_id
    account_id = payload.get("account_id")
    if (
        account_id is None
        or not isinstance(account_id, int)
        or isinstance(account_id, bool)
    ):
        return api_response(400, "交易帳戶為必填項目", None)
    account = db.session.get(Account, account_id)
    if not account:
        return api_response(400, "指定的帳戶不存在", None)

    # 3. 必填交易種類 trade_type
    trade_type_raw = payload.get("trade_type")
    if (
        not isinstance(trade_type_raw, str)
        or trade_type_raw.strip() not in ALLOWED_TRADE_TYPES
    ):
        return api_response(
            400,
            "交易種類不允許，只允許 buy、sell、cash_dividend、stock_dividend、drip、split、merge、capital_reduction",
            None,
        )
    trade_type = trade_type_raw.strip()

    # 4. 必填交易日期 traded_on
    traded_on_raw = payload.get("traded_on")
    if traded_on_raw is None or not str(traded_on_raw).strip():
        return api_response(400, "交易日期為必填項目", None)
    try:
        traded_on = date.fromisoformat(str(traded_on_raw).strip())
    except (ValueError, TypeError):
        return api_response(400, "交易日期格式不正確，請使用 YYYY-MM-DD 格式", None)

    # 5. 必填幣別 currency
    currency_raw = payload.get("currency")
    if (
        currency_raw is None
        or not isinstance(currency_raw, str)
        or len(currency_raw.strip()) != 3
    ):
        return api_response(400, "幣別代碼為必填項目，且必須為三碼英文字母", None)
    currency = currency_raw.strip().upper()

    # 6. 必填匯率 fx_rate_to_twd (大於 0)
    fx_rate_raw = payload.get("fx_rate_to_twd")
    if fx_rate_raw is None:
        return api_response(400, "折合台幣匯率為必填項目", None)
    try:
        fx_rate_to_twd = Decimal(str(fx_rate_raw))
    except (ValueError, TypeError, ArithmeticError):
        return api_response(400, "折合台幣匯率必須為有效數值", None)
    if fx_rate_to_twd <= 0:
        return api_response(400, "折合台幣匯率必須大於 0", None)

    # 7. 可選費用 fee 與稅費 tax (有值時 >= 0，送 null 與省略相同)
    fee = None
    fee_raw = payload.get("fee")
    if fee_raw is not None and str(fee_raw).strip():
        try:
            fee = Decimal(str(fee_raw))
        except (ValueError, TypeError, ArithmeticError):
            return api_response(400, "手續費必須為有效數值", None)
        if fee < 0:
            return api_response(400, "手續費必須大於或等於 0", None)

    tax = None
    tax_raw = payload.get("tax")
    if tax_raw is not None and str(tax_raw).strip():
        try:
            tax = Decimal(str(tax_raw))
        except (ValueError, TypeError, ArithmeticError):
            return api_response(400, "交易稅必須為有效數值", None)
        if tax < 0:
            return api_response(400, "交易稅必須大於或等於 0", None)

    # 8. 依交易種類檢查數量、價格、比例或現金金額
    quantity = None
    price = None
    cash_amount = None
    ratio = None

    # 當前持有數量 (供 sell 與 capital_reduction 驗證)
    current_holding, _, _ = calculate_holding(instrument.id)

    if trade_type in ("buy", "drip"):
        quantity_raw = payload.get("quantity")
        price_raw = payload.get("price")
        if quantity_raw is None or price_raw is None:
            return api_response(400, f"{trade_type} 交易必須提供數量與價格", None)
        try:
            quantity = Decimal(str(quantity_raw))
            price = Decimal(str(price_raw))
        except (ValueError, TypeError, ArithmeticError):
            return api_response(400, "數量與價格必須為有效數值", None)
        if quantity <= 0 or price <= 0:
            return api_response(400, "數量與價格必須大於 0", None)

        cash_amount_raw = payload.get("cash_amount")
        if cash_amount_raw is not None and str(cash_amount_raw).strip():
            try:
                cash_amount = Decimal(str(cash_amount_raw))
            except (ValueError, TypeError, ArithmeticError):
                return api_response(400, "現金金額必須為有效數值", None)
        else:
            cash_amount = (quantity * price) + (fee or Decimal("0")) + (tax or Decimal("0"))

    elif trade_type == "sell":
        quantity_raw = payload.get("quantity")
        price_raw = payload.get("price")
        if quantity_raw is None or price_raw is None:
            return api_response(400, "賣出交易必須提供數量與價格", None)
        try:
            quantity = Decimal(str(quantity_raw))
            price = Decimal(str(price_raw))
        except (ValueError, TypeError, ArithmeticError):
            return api_response(400, "數量與價格必須為有效數值", None)
        if quantity <= 0 or price <= 0:
            return api_response(400, "數量與價格必須大於 0", None)

        # 賣出不可超過目前持有數量
        if current_holding - quantity < 0:
            return api_response(400, "賣出數量超過目前持有數量", None)

        cash_amount_raw = payload.get("cash_amount")
        if cash_amount_raw is not None and str(cash_amount_raw).strip():
            try:
                cash_amount = Decimal(str(cash_amount_raw))
            except (ValueError, TypeError, ArithmeticError):
                return api_response(400, "現金金額必須為有效數值", None)
        else:
            cash_amount = (quantity * price) - (fee or Decimal("0")) - (tax or Decimal("0"))

    elif trade_type == "cash_dividend":
        cash_amount_raw = payload.get("cash_amount")
        if cash_amount_raw is None:
            return api_response(400, "現金股利交易必須提供現金金額", None)
        try:
            cash_amount = Decimal(str(cash_amount_raw))
        except (ValueError, TypeError, ArithmeticError):
            return api_response(400, "現金金額必須為有效數值", None)
        if cash_amount <= 0:
            return api_response(400, "現金金額必須大於 0", None)

    elif trade_type == "stock_dividend":
        quantity_raw = payload.get("quantity")
        if quantity_raw is None:
            return api_response(400, "股票股利交易必須提供股數數量", None)
        try:
            quantity = Decimal(str(quantity_raw))
        except (ValueError, TypeError, ArithmeticError):
            return api_response(400, "數量必須為有效數值", None)
        if quantity <= 0:
            return api_response(400, "數量必須大於 0", None)

    elif trade_type in ("split", "merge"):
        ratio_raw = payload.get("ratio")
        if ratio_raw is None:
            return api_response(400, f"{trade_type} 交易必須提供分割或合併比例 ratio", None)
        try:
            ratio = Decimal(str(ratio_raw))
        except (ValueError, TypeError, ArithmeticError):
            return api_response(400, "比例必須為有效數值", None)
        if ratio <= 0:
            return api_response(400, "比例必須大於 0", None)

    elif trade_type == "capital_reduction":
        ratio_raw = payload.get("ratio")
        quantity_raw = payload.get("quantity")
        cash_amount_raw = payload.get("cash_amount")

        if ratio_raw is None and quantity_raw is None and cash_amount_raw is None:
            return api_response(
                400, "減資交易必須提供比例、減少數量或退回現金金額至少一項", None
            )

        if ratio_raw is not None and str(ratio_raw).strip():
            try:
                ratio = Decimal(str(ratio_raw))
            except (ValueError, TypeError, ArithmeticError):
                return api_response(400, "減資比例必須為有效數值", None)
            if ratio <= 0:
                return api_response(400, "減資比例必須大於 0", None)

        if quantity_raw is not None and str(quantity_raw).strip():
            try:
                quantity = Decimal(str(quantity_raw))
            except (ValueError, TypeError, ArithmeticError):
                return api_response(400, "減資數量必須為有效數值", None)
            if quantity <= 0:
                return api_response(400, "減資數量必須大於 0", None)
            if current_holding - quantity < 0:
                return api_response(400, "減資扣減股數超過目前持有數量", None)

        if cash_amount_raw is not None and str(cash_amount_raw).strip():
            try:
                cash_amount = Decimal(str(cash_amount_raw))
            except (ValueError, TypeError, ArithmeticError):
                return api_response(400, "退回現金金額必須為有效數值", None)
            if cash_amount <= 0:
                return api_response(400, "退回現金金額必須大於 0", None)

    # 9. 檢查 post_income 需求
    post_income = payload.get("post_income") is True
    income_category = None
    if (
        post_income
        and trade_type in ("cash_dividend", "capital_reduction")
        and cash_amount is not None
        and cash_amount > 0
    ):
        income_cat_id = payload.get("income_category_id")
        if (
            income_cat_id is None
            or not isinstance(income_cat_id, int)
            or isinstance(income_cat_id, bool)
        ):
            return api_response(
                400, "post_income 為真時必須提供入帳分類 income_category_id", None
            )
        income_category = db.session.get(IncomeCategory, income_cat_id)
        if not income_category:
            return api_response(400, "指定的入帳分類不存在", None)

    trade = Trade(
        instrument_id=instrument.id,
        account_id=account.id,
        trade_type=trade_type,
        traded_on=traded_on,
        quantity=quantity,
        price=price,
        cash_amount=cash_amount,
        ratio=ratio,
        fee=fee,
        tax=tax,
        currency=currency,
        fx_rate_to_twd=fx_rate_to_twd,
    )
    db.session.add(trade)
    db.session.flush()

    if income_category and cash_amount and cash_amount > 0:
        income = Income(
            received_on=trade.traded_on,
            amount=cash_amount,
            currency=trade.currency,
            fx_rate_to_twd=trade.fx_rate_to_twd,
            category_id=income_category.id,
            account_id=trade.account_id,
            source=f"{instrument.symbol} {trade_type}",
            note=f"{instrument.name} 投資交易現金入帳",
            trade_id=trade.id,
        )
        db.session.add(income)

    db.session.commit()

    return api_response(201, "投資交易新增成功", trade.to_dict())


@trades_bp.get("")
def list_trades():
    """取得投資交易清單。可依 instrument_id、account_id 篩選。"""
    stmt = db.select(Trade)

    instrument_id_param = request.args.get("instrument_id")
    if instrument_id_param is not None and instrument_id_param.strip():
        try:
            instrument_id = int(instrument_id_param.strip())
        except ValueError:
            return api_response(400, "標的代碼格式不正確", None)
        stmt = stmt.where(Trade.instrument_id == instrument_id)

    account_id_param = request.args.get("account_id")
    if account_id_param is not None and account_id_param.strip():
        try:
            account_id = int(account_id_param.strip())
        except ValueError:
            return api_response(400, "帳戶代碼格式不正確", None)
        stmt = stmt.where(Trade.account_id == account_id)

    stmt = stmt.order_by(Trade.traded_on.desc(), Trade.id.desc())
    trades = db.session.scalars(stmt).all()
    return api_response(200, "取得投資交易清單成功", [t.to_dict() for t in trades])


@trades_bp.post("/<int:trade_id>/void")
def void_trade(trade_id: int):
    """作廢一筆投資交易。

    寫入 voided_at。若這筆交易已有入帳，回 400，不要作廢。
    """
    trade = db.session.get(Trade, trade_id)
    if not trade:
        return api_response(404, "找不到指定的交易", None)

    # 檢查是否已有關聯入帳
    linked_income = db.session.scalar(
        db.select(Income).filter_by(trade_id=trade.id)
    )
    if linked_income:
        return api_response(400, "此交易已有入帳記錄，無法作廢", None)

    trade.voided_at = datetime.now(timezone.utc)
    trade.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return api_response(200, "交易已成功作廢", trade.to_dict())
