"""
Pydantic schemas for the GemBlast ETL pipeline.

PlayerEvent  – one raw row from player_events.csv
PlayerRecord – one aggregated row written to the `players` Supabase table
SessionRecord – one aggregated row written to the `sessions` Supabase table
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, field_validator, model_validator

CohortType = Literal["whale", "mid", "f2p"]
EventType = Literal["session_start", "level_complete", "purchase", "ad_watched"]


class PlayerEvent(BaseModel):
    event_id: str
    player_id: str
    cohort: CohortType
    install_date: date
    days_since_install: int
    event_type: EventType
    event_time: datetime
    session_id: str
    level_id: Optional[int] = None
    amount_usd: Optional[float] = None

    @field_validator("days_since_install")
    @classmethod
    def days_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"days_since_install must be >= 0, got {v}")
        return v

    @field_validator("amount_usd")
    @classmethod
    def amount_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError(f"amount_usd must be positive, got {v}")
        return v

    @model_validator(mode="after")
    def purchase_amount_consistency(self) -> "PlayerEvent":
        if self.event_type == "purchase" and self.amount_usd is None:
            raise ValueError("purchase events must have amount_usd set")
        if self.event_type != "purchase" and self.amount_usd is not None:
            raise ValueError(
                f"amount_usd must be null for event_type={self.event_type!r}"
            )
        return self


class PlayerRecord(BaseModel):
    """One row in the `players` Supabase table — RFM per player."""

    player_id: str
    cohort: CohortType
    install_date: date
    first_seen: datetime
    last_seen: datetime
    recency_days: int   # days between last_seen and the dataset reference date
    frequency: int      # unique sessions played
    monetary: float     # total USD spent


class SessionRecord(BaseModel):
    """One row in the `sessions` Supabase table — metrics per session."""

    session_id: str
    player_id: str
    cohort: CohortType
    session_start: datetime
    days_since_install: int
    levels_completed: int
    ads_watched: int
    revenue: float
