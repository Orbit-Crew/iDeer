"""Durable original dispatch identity and one receipt/evidence projection."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Index, String, Text, false, text
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


class DeviceTaskReceiptModel(Base):
    __tablename__ = "device_control_task_receipts"

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    binding: Mapped[dict] = mapped_column(JSON, nullable=False)
    task: Mapped[dict] = mapped_column(JSON, nullable=False)
    receipt_id: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    receipt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    receipt: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    acknowledgment: Mapped[str | None] = mapped_column(Text, nullable=True)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default=text("''"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="result_not_verified", server_default=text("'result_not_verified'"))
    stop_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    recovery_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_receipt: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (Index("ix_device_task_thread_history", "owner_id", "thread_id", "created_at", "task_id"),)
