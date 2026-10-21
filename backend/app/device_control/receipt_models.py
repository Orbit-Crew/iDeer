"""Durable original dispatch identity and one receipt/evidence projection."""

from __future__ import annotations

from sqlalchemy import JSON, String, Text
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
