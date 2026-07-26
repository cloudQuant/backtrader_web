import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class PortfolioLedgerModel(Base):
    __tablename__ = "portfolio_ledgers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    base_currency = Column(String(20), nullable=False, default="CNY")
    source_type = Column(String(50), nullable=False, default="manual")
    benchmark_symbol = Column(String(50), nullable=True)
    tags = Column(JSON, nullable=False, default=list)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    transactions = relationship(
        "PortfolioLedgerTransactionModel",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        order_by="PortfolioLedgerTransactionModel.trade_date",
    )
    imports = relationship(
        "PortfolioLedgerImportModel",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        order_by="PortfolioLedgerImportModel.created_at",
    )
    snapshots = relationship(
        "PortfolioLedgerSnapshotModel",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        order_by="PortfolioLedgerSnapshotModel.snapshot_index",
    )


class PortfolioLedgerImportModel(Base):
    __tablename__ = "portfolio_ledger_imports"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "idempotency_key",
            name="uq_portfolio_ledger_imports_portfolio_idempotency",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    portfolio_id = Column(
        String(36),
        ForeignKey("portfolio_ledgers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    import_format = Column(String(20), nullable=False, default="json")
    idempotency_key = Column(String(128), nullable=False, index=True)
    imported_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    portfolio = relationship("PortfolioLedgerModel", back_populates="imports")


class PortfolioLedgerTransactionModel(Base):
    __tablename__ = "portfolio_ledger_transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    portfolio_id = Column(
        String(36),
        ForeignKey("portfolio_ledgers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol = Column(String(50), nullable=False, default="")
    trade_type = Column(String(30), nullable=False, index=True)
    quantity = Column(Float, nullable=False, default=0.0)
    price = Column(Float, nullable=False, default=0.0)
    amount = Column(Float, nullable=True)
    trade_date = Column(String(20), nullable=False, index=True)
    benchmark_symbol = Column(String(50), nullable=True)
    tags = Column(JSON, nullable=False, default=list)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    portfolio = relationship("PortfolioLedgerModel", back_populates="transactions")


class PortfolioLedgerSnapshotModel(Base):
    __tablename__ = "portfolio_ledger_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "snapshot_date",
            "snapshot_index",
            name="uq_portfolio_ledger_snapshots_portfolio_date_index",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    portfolio_id = Column(
        String(36),
        ForeignKey("portfolio_ledgers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_date = Column(String(20), nullable=False, index=True)
    snapshot_index = Column(Integer, nullable=False)
    cash_flow = Column(Float, nullable=False, default=0.0)
    nav = Column(Float, nullable=False, default=1_000_000.0)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    portfolio = relationship("PortfolioLedgerModel", back_populates="snapshots")
