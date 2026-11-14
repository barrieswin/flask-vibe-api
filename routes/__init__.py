"""API 路由模組。"""

from .accounts import accounts_bp
from .draw_periods import draw_periods_bp
from .expense_categories import expense_categories_bp
from .expenses import expenses_bp
from .income_categories import income_categories_bp
from .incomes import incomes_bp
from .instruments import instruments_bp
from .invoices import invoices_bp
from .trades import trades_bp
from .transfers import transfers_bp

__all__ = [
    "accounts_bp",
    "transfers_bp",
    "income_categories_bp",
    "incomes_bp",
    "expense_categories_bp",
    "expenses_bp",
    "invoices_bp",
    "draw_periods_bp",
    "instruments_bp",
    "trades_bp",
]




