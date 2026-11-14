"""投資標的相關 API 路由。"""

from decimal import Decimal

from flask import Blueprint, request

from extensions import db
from models import Instrument, Trade
from utils import api_response

instruments_bp = Blueprint("instruments", __name__, url_prefix="/api/instruments")

ALLOWED_MARKETS = {"tw_stock", "us_stock", "fund", "other"}


def calculate_holding(instrument_id: int):
    """計算標的之目前持有數量與平均買進成本。

    忽略 voided_at 有值的交易，依 traded_on ASC, id ASC 重播。
    平均成本只納入 buy 與 drip 的價格和數量。
    賣出後成本依平均成本等比例減少。
    stock_dividend 增加股數、不增加成本。
    split 與 merge 用 ratio 調整股數，總成本不變。
    """
    trades = db.session.scalars(
        db.select(Trade)
        .where(
            Trade.instrument_id == instrument_id,
            Trade.voided_at.is_(None),
        )
        .order_by(Trade.traded_on.asc(), Trade.id.asc())
    ).all()

    current_qty = Decimal("0")
    total_cost = Decimal("0")

    for tr in trades:
        qty = tr.quantity or Decimal("0")
        prc = tr.price or Decimal("0")

        if tr.trade_type in ("buy", "drip"):
            current_qty += qty
            total_cost += qty * prc
        elif tr.trade_type == "sell":
            if current_qty > 0:
                avg_cost = total_cost / current_qty
                total_cost -= qty * avg_cost
                current_qty -= qty
            else:
                current_qty = Decimal("0")
                total_cost = Decimal("0")
            if current_qty <= 0:
                current_qty = Decimal("0")
                total_cost = Decimal("0")
        elif tr.trade_type == "stock_dividend":
            current_qty += qty
        elif tr.trade_type in ("split", "merge"):
            if tr.ratio and tr.ratio > 0:
                current_qty = current_qty * tr.ratio
        elif tr.trade_type == "capital_reduction":
            if tr.ratio and tr.ratio > 0:
                current_qty = current_qty * tr.ratio
            elif tr.quantity and tr.quantity > 0:
                if current_qty > 0:
                    avg_cost = total_cost / current_qty
                    total_cost -= tr.quantity * avg_cost
                    current_qty -= tr.quantity
                if current_qty <= 0:
                    current_qty = Decimal("0")
                    total_cost = Decimal("0")
        elif tr.trade_type == "cash_dividend":
            pass

    if current_qty > 0 and total_cost > 0:
        avg_cost = total_cost / current_qty
    else:
        avg_cost = Decimal("0")

    return current_qty, avg_cost, total_cost


@instruments_bp.post("")
def create_instrument():
    """新增投資標的。必填 market、symbol、name、currency。成功回傳 201。"""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_response(400, "請提供合法的 JSON 物件格式", None)

    # 1. 必填 market
    market_raw = payload.get("market")
    if not isinstance(market_raw, str) or market_raw.strip() not in ALLOWED_MARKETS:
        return api_response(
            400,
            "市場別不在允許清單中，只允許 tw_stock、us_stock、fund、other",
            None,
        )
    market = market_raw.strip()

    # 2. 必填 symbol
    symbol_raw = payload.get("symbol")
    if not isinstance(symbol_raw, str) or not symbol_raw.strip():
        return api_response(400, "標的代號為必填項目且不可為空", None)
    symbol = symbol_raw.strip().upper()

    # 檢查同一市場與代號重複
    existing = db.session.scalar(
        db.select(Instrument).filter_by(market=market, symbol=symbol)
    )
    if existing:
        return api_response(400, "該市場下已存在相同的標的代號，不可重複", None)

    # 3. 必填 name
    name_raw = payload.get("name")
    if not isinstance(name_raw, str) or not name_raw.strip():
        return api_response(400, "標的名稱為必填項目且不可為空", None)
    name = name_raw.strip()

    # 4. 必填 currency
    currency_raw = payload.get("currency")
    if (
        currency_raw is None
        or not isinstance(currency_raw, str)
        or len(currency_raw.strip()) != 3
    ):
        return api_response(400, "幣別代碼為必填項目，且必須為三碼英文字母", None)
    currency = currency_raw.strip().upper()

    instrument = Instrument(
        market=market,
        symbol=symbol,
        name=name,
        currency=currency,
    )
    db.session.add(instrument)
    db.session.commit()

    return api_response(201, "投資標的新增成功", instrument.to_dict())


@instruments_bp.get("")
def list_instruments():
    """取得投資標的清單。若無資料回傳 200 與空清單。"""
    instruments = db.session.scalars(
        db.select(Instrument).order_by(Instrument.id.asc())
    ).all()
    return api_response(
        200, "取得投資標的清單成功", [inst.to_dict() for inst in instruments]
    )


@instruments_bp.get("/<int:instrument_id>")
def get_instrument(instrument_id: int):
    """取得單一投資標的。若無該列回傳 404。"""
    instrument = db.session.get(Instrument, instrument_id)
    if not instrument:
        return api_response(404, "找不到指定的投資標的", None)
    return api_response(200, "取得投資標的成功", instrument.to_dict())


@instruments_bp.get("/<int:instrument_id>/holding")
def get_instrument_holding(instrument_id: int):
    """取得標的目前持有股數與平均買進成本。

    忽略 voided_at 有值的交易，依 traded_on、id 重播。
    """
    instrument = db.session.get(Instrument, instrument_id)
    if not instrument:
        return api_response(404, "找不到指定的投資標的", None)

    current_qty, avg_cost, total_cost = calculate_holding(instrument.id)

    data = {
        "instrument_id": instrument.id,
        "market": instrument.market,
        "symbol": instrument.symbol,
        "name": instrument.name,
        "currency": instrument.currency,
        "quantity": float(round(current_qty, 4)),
        "average_cost": float(round(avg_cost, 4)),
        "total_cost": float(round(total_cost, 4)),
    }
    return api_response(200, "取得標的持有狀況成功", data)
