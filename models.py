"""資料庫模型定義。

包含帳戶（Account）與帳戶移轉（Transfer）模型。
"""

from datetime import datetime, timezone
from decimal import Decimal

from extensions import db

__all__ = ["Account", "Transfer"]


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
