"""資料庫模型定義。

包含帳戶（Account）、帳戶移轉（Transfer）、統一發票（Invoice）、發票品項（InvoiceItem）、開獎期別（DrawPeriod）、開獎獎項（DrawPrize）、入帳分類（IncomeCategory）、入帳記錄（Income）、花費分類（ExpenseCategory）與花費記錄（Expense）模型。
"""

from datetime import datetime, timezone
from decimal import Decimal

from extensions import db

__all__ = [
    "Account",
    "Transfer",
    "Invoice",
    "InvoiceItem",
    "DrawPeriod",
    "DrawPrize",
    "IncomeCategory",
    "Income",
    "ExpenseCategory",
    "Expense",
]


class Account(db.Model):
    """帳戶模型（accounts 表）。

    記錄現金、銀行、信用卡、券商交割戶等各類資金載體。
    """

    __tablename__ = "accounts"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    currency = db.Column(
        db.String(3),
        nullable=False,
        default="TWD",
        server_default="TWD",
    )
    opening_balance = db.Column(
        db.Numeric(16, 4),
        nullable=False,
        default=Decimal("0.0000"),
        server_default=db.text("0"),
    )
    statement_day = db.Column(db.Integer, nullable=True)
    payment_day = db.Column(db.Integer, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint("name", name="uq_accounts_name"),
        db.CheckConstraint(
            "kind IN ('cash', 'bank', 'credit_card', 'broker')",
            name="ck_accounts_kind",
        ),
        db.CheckConstraint(
            "statement_day IS NULL OR (statement_day >= 1 AND statement_day <= 31)",
            name="ck_accounts_statement_day",
        ),
        db.CheckConstraint(
            "payment_day IS NULL OR (payment_day >= 1 AND payment_day <= 31)",
            name="ck_accounts_payment_day",
        ),
    )

    transfers_from = db.relationship(
        "Transfer",
        foreign_keys="Transfer.from_account_id",
        back_populates="from_account",
        passive_deletes=True,
    )
    transfers_to = db.relationship(
        "Transfer",
        foreign_keys="Transfer.to_account_id",
        back_populates="to_account",
        passive_deletes=True,
    )
    incomes = db.relationship(
        "Income",
        foreign_keys="Income.account_id",
        back_populates="account",
        passive_deletes=True,
    )
    expenses = db.relationship(
        "Expense",
        foreign_keys="Expense.account_id",
        back_populates="account",
        passive_deletes=True,
    )

    def to_dict(self) -> dict:
        """轉換為字典供 API 回傳。"""
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "currency": self.currency,
            "opening_balance": float(self.opening_balance) if self.opening_balance is not None else 0.0,
            "statement_day": self.statement_day,
            "payment_day": self.payment_day,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<Account id={self.id} name={self.name!r} kind={self.kind!r}>"


class Transfer(db.Model):
    """帳戶移轉模型（transfers 表）。

    記錄內部帳戶間的資金移轉與換匯。
    """

    __tablename__ = "transfers"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    transferred_on = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(16, 4), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    fx_rate_to_twd = db.Column(
        db.Numeric(12, 6),
        nullable=False,
        default=Decimal("1.000000"),
        server_default=db.text("1.000000"),
    )
    from_account_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "accounts.id",
            name="fk_transfers_from_account_id_accounts",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    to_account_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "accounts.id",
            name="fk_transfers_to_account_id_accounts",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    note = db.Column(db.String(255), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.CheckConstraint("amount > 0", name="ck_transfers_amount"),
        db.CheckConstraint("fx_rate_to_twd > 0", name="ck_transfers_fx_rate_to_twd"),
        db.CheckConstraint(
            "from_account_id <> to_account_id",
            name="ck_transfers_different_accounts",
        ),
    )

    from_account = db.relationship(
        "Account",
        foreign_keys=[from_account_id],
        back_populates="transfers_from",
    )
    to_account = db.relationship(
        "Account",
        foreign_keys=[to_account_id],
        back_populates="transfers_to",
    )

    def to_dict(self) -> dict:
        """轉換為字典供 API 回傳。"""
        return {
            "id": self.id,
            "transferred_on": self.transferred_on.isoformat() if self.transferred_on else None,
            "amount": float(self.amount) if self.amount is not None else 0.0,
            "currency": self.currency,
            "fx_rate_to_twd": float(self.fx_rate_to_twd) if self.fx_rate_to_twd is not None else 1.0,
            "from_account_id": self.from_account_id,
            "to_account_id": self.to_account_id,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<Transfer id={self.id} on={self.transferred_on} "
            f"amount={self.amount} {self.currency} "
            f"from={self.from_account_id} to={self.to_account_id}>"
        )


class Invoice(db.Model):
    """統一發票模型（invoices 表）。

    記錄發票號碼、開立日期、金額、種類、幣別、匯率、隨機碼、賣方資訊與對獎狀態。
    """

    __tablename__ = "invoices"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    number = db.Column(db.String(10), nullable=False)
    issued_on = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(16, 4), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    currency = db.Column(
        db.String(3),
        nullable=False,
        default="TWD",
        server_default="TWD",
    )
    fx_rate_to_twd = db.Column(
        db.Numeric(12, 6),
        nullable=False,
        default=Decimal("1.000000"),
        server_default=db.text("1.000000"),
    )
    random_code = db.Column(db.String(4), nullable=True)
    seller_name = db.Column(db.String(100), nullable=True)
    seller_ban = db.Column(db.String(8), nullable=True)
    prize_status = db.Column(
        db.String(20),
        nullable=False,
        default="unchecked",
        server_default="unchecked",
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint("number", name="uq_invoices_number"),
        db.CheckConstraint(
            "number ~ '^[A-Z]{2}[0-9]{8}$'",
            name="ck_invoices_number",
        ),
        db.CheckConstraint("amount > 0", name="ck_invoices_amount"),
        db.CheckConstraint(
            "kind IN ('paper', 'electronic')",
            name="ck_invoices_kind",
        ),
        db.CheckConstraint("fx_rate_to_twd > 0", name="ck_invoices_fx_rate_to_twd"),
        db.CheckConstraint(
            "random_code IS NULL OR random_code ~ '^[0-9]{4}$'",
            name="ck_invoices_random_code",
        ),
        db.CheckConstraint(
            "prize_status IN ('unchecked', 'lost', 'won', 'claimed', 'void')",
            name="ck_invoices_prize_status",
        ),
    )

    items = db.relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    income = db.relationship(
        "Income",
        back_populates="invoice",
        uselist=False,
        passive_deletes=True,
    )
    expenses = db.relationship(
        "Expense",
        back_populates="invoice",
        passive_deletes=True,
    )

    def to_dict(self) -> dict:
        """轉換為字典供 API 回傳。"""
        return {
            "id": self.id,
            "number": self.number,
            "issued_on": self.issued_on.isoformat() if self.issued_on else None,
            "amount": float(self.amount) if self.amount is not None else 0.0,
            "kind": self.kind,
            "currency": self.currency,
            "fx_rate_to_twd": float(self.fx_rate_to_twd) if self.fx_rate_to_twd is not None else 1.0,
            "random_code": self.random_code,
            "seller_name": self.seller_name,
            "seller_ban": self.seller_ban,
            "prize_status": self.prize_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<Invoice id={self.id} number={self.number!r} amount={self.amount} status={self.prize_status!r}>"


class InvoiceItem(db.Model):
    """發票品項明細模型（invoice_items 表）。

    記錄發票所屬品項名稱、數量、單價與金額小計。
    """

    __tablename__ = "invoice_items"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    invoice_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "invoices.id",
            name="fk_invoice_items_invoice_id_invoices",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    name = db.Column(db.String(150), nullable=False)
    quantity = db.Column(db.Numeric(16, 4), nullable=False)
    unit_price = db.Column(db.Numeric(16, 4), nullable=False)
    line_amount = db.Column(db.Numeric(16, 4), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_invoice_items_quantity"),
        db.CheckConstraint("unit_price > 0", name="ck_invoice_items_unit_price"),
        db.CheckConstraint("line_amount > 0", name="ck_invoice_items_line_amount"),
    )

    invoice = db.relationship(
        "Invoice",
        back_populates="items",
    )

    def to_dict(self) -> dict:
        """轉換為字典供 API 回傳。"""
        return {
            "id": self.id,
            "invoice_id": self.invoice_id,
            "name": self.name,
            "quantity": float(self.quantity) if self.quantity is not None else 0.0,
            "unit_price": float(self.unit_price) if self.unit_price is not None else 0.0,
            "line_amount": float(self.line_amount) if self.line_amount is not None else 0.0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<InvoiceItem id={self.id} invoice_id={self.invoice_id} name={self.name!r} line_amount={self.line_amount}>"


class DrawPeriod(db.Model):
    """統一發票開獎期別模型（draw_periods 表）。

    記錄發票開獎期別標識（如 2024-02 等）。
    """

    __tablename__ = "draw_periods"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    period_key = db.Column(db.String(20), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint("period_key", name="uq_draw_periods_period_key"),
    )

    prizes = db.relationship(
        "DrawPrize",
        back_populates="draw_period",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def to_dict(self) -> dict:
        """轉換為字典供 API 回傳。"""
        return {
            "id": self.id,
            "period_key": self.period_key,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<DrawPeriod id={self.id} period_key={self.period_key!r}>"


class DrawPrize(db.Model):
    """統一發票開獎獎項模型（draw_prizes 表）。

    記錄各期別的開獎獎項、中獎號碼與獎金金額。
    """

    __tablename__ = "draw_prizes"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    draw_period_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "draw_periods.id",
            name="fk_draw_prizes_draw_period_id_draw_periods",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    tier = db.Column(db.String(20), nullable=False)
    matching_number = db.Column(db.String(10), nullable=False)
    amount = db.Column(db.Numeric(16, 4), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "draw_period_id",
            "tier",
            "matching_number",
            name="uq_draw_prizes_draw_period_id_tier_matching_number",
        ),
        db.CheckConstraint(
            "tier IN ('special', 'grand', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'extra_sixth')",
            name="ck_draw_prizes_tier",
        ),
        db.CheckConstraint("amount >= 0", name="ck_draw_prizes_amount"),
    )

    draw_period = db.relationship(
        "DrawPeriod",
        back_populates="prizes",
    )

    def to_dict(self) -> dict:
        """轉換為字典供 API 回傳。"""
        return {
            "id": self.id,
            "draw_period_id": self.draw_period_id,
            "tier": self.tier,
            "matching_number": self.matching_number,
            "amount": float(self.amount) if self.amount is not None else 0.0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<DrawPrize id={self.id} draw_period_id={self.draw_period_id} "
            f"tier={self.tier!r} matching_number={self.matching_number!r} amount={self.amount}>"
        )


class IncomeCategory(db.Model):
    """入帳分類模型（income_categories 表）。

    記錄收入商業性質分類（如薪資、獎金、利息、發票中獎等）。
    """

    __tablename__ = "income_categories"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint("name", name="uq_income_categories_name"),
    )

    incomes = db.relationship(
        "Income",
        back_populates="category",
        passive_deletes=True,
    )

    def to_dict(self) -> dict:
        """轉換為字典供 API 回傳。"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<IncomeCategory id={self.id} name={self.name!r}>"


class Income(db.Model):
    """入帳記錄模型（incomes 表）。

    記錄所有正向現金流入帳流水。
    """

    __tablename__ = "incomes"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    received_on = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(16, 4), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    fx_rate_to_twd = db.Column(
        db.Numeric(12, 6),
        nullable=False,
        default=Decimal("1.000000"),
        server_default=db.text("1.000000"),
    )
    category_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "income_categories.id",
            name="fk_incomes_category_id_income_categories",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    account_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "accounts.id",
            name="fk_incomes_account_id_accounts",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    source = db.Column(db.String(100), nullable=True)
    note = db.Column(db.String(255), nullable=True)
    invoice_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "invoices.id",
            name="fk_incomes_invoice_id_invoices",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint("invoice_id", name="uq_incomes_invoice_id"),
        db.CheckConstraint("amount > 0", name="ck_incomes_amount"),
        db.CheckConstraint("fx_rate_to_twd > 0", name="ck_incomes_fx_rate_to_twd"),
        db.CheckConstraint(
            "source IS NOT NULL OR note IS NOT NULL",
            name="ck_incomes_source_or_note_present",
        ),
    )

    category = db.relationship(
        "IncomeCategory",
        foreign_keys=[category_id],
        back_populates="incomes",
    )
    account = db.relationship(
        "Account",
        foreign_keys=[account_id],
        back_populates="incomes",
    )
    invoice = db.relationship(
        "Invoice",
        foreign_keys=[invoice_id],
        back_populates="income",
    )

    def to_dict(self) -> dict:
        """轉換為字典供 API 回傳。"""
        return {
            "id": self.id,
            "received_on": self.received_on.isoformat() if self.received_on else None,
            "amount": float(self.amount) if self.amount is not None else 0.0,
            "currency": self.currency,
            "fx_rate_to_twd": float(self.fx_rate_to_twd) if self.fx_rate_to_twd is not None else 1.0,
            "category_id": self.category_id,
            "account_id": self.account_id,
            "source": self.source,
            "note": self.note,
            "invoice_id": self.invoice_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<Income id={self.id} on={self.received_on} "
            f"amount={self.amount} {self.currency} "
            f"category={self.category_id} account={self.account_id}>"
        )


class ExpenseCategory(db.Model):
    """花費分類模型（expense_categories 表）。

    記錄支出的商業性質分類（如餐飲食品、日常交通、水電瓦斯等）。
    """

    __tablename__ = "expense_categories"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint("name", name="uq_expense_categories_name"),
    )

    expenses = db.relationship(
        "Expense",
        back_populates="category",
        passive_deletes=True,
    )

    def to_dict(self) -> dict:
        """轉換為字典供 API 回傳。"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<ExpenseCategory id={self.id} name={self.name!r}>"


class Expense(db.Model):
    """花費記錄模型（expenses 表）。

    記錄所有實體資金流出的開銷明細。
    """

    __tablename__ = "expenses"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    spent_on = db.Column(db.Date, nullable=False)
    settled_on = db.Column(db.Date, nullable=True)
    amount = db.Column(db.Numeric(16, 4), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    fx_rate_to_twd = db.Column(
        db.Numeric(12, 6),
        nullable=False,
        default=Decimal("1.000000"),
        server_default=db.text("1.000000"),
    )
    category_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "expense_categories.id",
            name="fk_expenses_category_id_expense_categories",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    account_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "accounts.id",
            name="fk_expenses_account_id_accounts",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    merchant = db.Column(db.String(100), nullable=True)
    note = db.Column(db.String(255), nullable=True)
    invoice_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "invoices.id",
            name="fk_expenses_invoice_id_invoices",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.CheckConstraint("amount > 0", name="ck_expenses_amount"),
        db.CheckConstraint("fx_rate_to_twd > 0", name="ck_expenses_fx_rate_to_twd"),
        db.CheckConstraint(
            "merchant IS NOT NULL OR note IS NOT NULL",
            name="ck_expenses_merchant_or_note_present",
        ),
    )

    category = db.relationship(
        "ExpenseCategory",
        foreign_keys=[category_id],
        back_populates="expenses",
    )
    account = db.relationship(
        "Account",
        foreign_keys=[account_id],
        back_populates="expenses",
    )
    invoice = db.relationship(
        "Invoice",
        foreign_keys=[invoice_id],
        back_populates="expenses",
    )

    def to_dict(self) -> dict:
        """轉換為字典供 API 回傳。"""
        return {
            "id": self.id,
            "spent_on": self.spent_on.isoformat() if self.spent_on else None,
            "settled_on": self.settled_on.isoformat() if self.settled_on else None,
            "amount": float(self.amount) if self.amount is not None else 0.0,
            "currency": self.currency,
            "fx_rate_to_twd": float(self.fx_rate_to_twd) if self.fx_rate_to_twd is not None else 1.0,
            "category_id": self.category_id,
            "account_id": self.account_id,
            "merchant": self.merchant,
            "note": self.note,
            "invoice_id": self.invoice_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<Expense id={self.id} on={self.spent_on} "
            f"amount={self.amount} {self.currency} "
            f"category={self.category_id} account={self.account_id}>"
        )



