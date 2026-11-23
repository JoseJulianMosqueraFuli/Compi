"""HealthKit samples and the last committed page from each single-user stream."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Column, DateTime, Index
from sqlmodel import Field, SQLModel


class HealthSyncCursor(SQLModel, table=True):
    __tablename__ = "health_sync_cursor"

    kind: str = Field(primary_key=True, max_length=20)
    stream_id: UUID = Field(unique=True)
    last_sequence: int = Field(sa_column=Column(BigInteger, nullable=False))
    last_digest: str = Field(max_length=64)
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class HealthObservation(SQLModel, table=True):
    """Current source record. Numeric values use bpm or kg according to kind."""

    __tablename__ = "health_observation"
    __table_args__ = (Index("ix_health_observation_kind_start", "kind", "start"),)

    kind: str = Field(primary_key=True, foreign_key="health_sync_cursor.kind", max_length=20)
    sample_id: UUID = Field(primary_key=True)
    source_bundle: str = Field(max_length=255)
    start: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    end: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    numeric_value: float | None = None
    category_value: str | None = Field(default=None, max_length=20)
    duration_s: float | None = None
