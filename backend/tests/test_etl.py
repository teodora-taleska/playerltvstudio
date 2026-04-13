"""
Tests for etl/schemas.py and etl/pipeline.py.

Covers:
- PlayerEvent schema validation (valid cases, each invalid case)
- validate_events() row filtering
- aggregate_rfm() recency / frequency / monetary correctness
- aggregate_sessions() per-session metrics correctness
"""

from datetime import date, datetime

import pandas as pd
import pytest
from pydantic import ValidationError

from etl.pipeline import aggregate_rfm, aggregate_sessions, validate_events
from etl.schemas import PlayerEvent


# Helpers

def make_event(**overrides) -> dict:
    """Return a valid session_start event dict; override any field as needed."""
    base: dict = {
        "event_id": "evt-001",
        "player_id": "p_00001",
        "cohort": "mid",
        "install_date": date(2024, 1, 1),
        "days_since_install": 0,
        "event_type": "session_start",
        "event_time": datetime(2024, 1, 1, 10, 0, 0),
        "session_id": "sess-001",
        "level_id": None,
        "amount_usd": None,
    }
    base.update(overrides)
    return base


def make_df(events: list[dict]) -> pd.DataFrame:
    """Build a typed DataFrame from a list of event dicts."""
    df = pd.DataFrame(events)
    df["event_time"] = pd.to_datetime(df["event_time"])
    df["install_date"] = pd.to_datetime(df["install_date"]).dt.date
    return df



# Schema validation — PlayerEvent

class TestPlayerEventValid:
    def test_session_start(self):
        e = PlayerEvent.model_validate(make_event())
        assert e.player_id == "p_00001"
        assert e.amount_usd is None

    def test_level_complete(self):
        e = PlayerEvent.model_validate(make_event(event_type="level_complete", level_id=5))
        assert e.level_id == 5

    def test_ad_watched(self):
        e = PlayerEvent.model_validate(make_event(event_type="ad_watched"))
        assert e.event_type == "ad_watched"

    def test_purchase(self):
        e = PlayerEvent.model_validate(make_event(event_type="purchase", amount_usd=9.99))
        assert e.amount_usd == pytest.approx(9.99)

    def test_all_cohorts_accepted(self):
        for cohort in ("whale", "mid", "f2p"):
            e = PlayerEvent.model_validate(make_event(cohort=cohort))
            assert e.cohort == cohort

    def test_days_since_install_zero(self):
        e = PlayerEvent.model_validate(make_event(days_since_install=0))
        assert e.days_since_install == 0


class TestPlayerEventInvalid:
    def test_invalid_cohort(self):
        with pytest.raises(ValidationError):
            PlayerEvent.model_validate(make_event(cohort="vip"))

    def test_invalid_event_type(self):
        with pytest.raises(ValidationError):
            PlayerEvent.model_validate(make_event(event_type="login"))

    def test_negative_days_since_install(self):
        with pytest.raises(ValidationError):
            PlayerEvent.model_validate(make_event(days_since_install=-1))

    def test_purchase_missing_amount(self):
        with pytest.raises(ValidationError):
            PlayerEvent.model_validate(make_event(event_type="purchase", amount_usd=None))

    def test_non_purchase_has_amount(self):
        with pytest.raises(ValidationError):
            PlayerEvent.model_validate(make_event(event_type="session_start", amount_usd=4.99))

    def test_zero_amount_usd(self):
        with pytest.raises(ValidationError):
            PlayerEvent.model_validate(make_event(event_type="purchase", amount_usd=0.0))

    def test_negative_amount_usd(self):
        with pytest.raises(ValidationError):
            PlayerEvent.model_validate(make_event(event_type="purchase", amount_usd=-5.00))

    def test_missing_required_field(self):
        bad = make_event()
        del bad["player_id"]
        with pytest.raises(ValidationError):
            PlayerEvent.model_validate(bad)



# validate_events()



class TestValidateEvents:
    def test_all_valid_rows_pass(self):
        df = make_df([make_event(event_id="e1"), make_event(event_id="e2")])
        valid_df, errors = validate_events(df)
        assert len(valid_df) == 2
        assert errors == 0

    def test_invalid_row_is_dropped(self):
        events = [make_event(event_id="e1"), make_event(event_id="e2", cohort="bad")]
        df = make_df(events)
        valid_df, errors = validate_events(df)
        assert len(valid_df) == 1
        assert errors == 1

    def test_all_invalid_returns_empty_df(self):
        df = make_df([make_event(cohort="bad")])
        valid_df, errors = validate_events(df)
        assert valid_df.empty
        assert errors == 1

    def test_error_count_accumulates(self):
        events = [make_event(event_id=f"e{i}", cohort="bad") for i in range(5)]
        df = make_df(events)
        _, errors = validate_events(df)
        assert errors == 5



# aggregate_rfm()

#
# Dataset:
#   p_00001 (whale)
#     session s1  day 0 – session_start + purchase $9.99
#     session s2  day 1 – session_start only
#   p_00002 (f2p)
#     session s3  day 0 – session_start only
#
# reference_date = max(event_time) = 2024-01-02 10:00
# Expected RFM:
#   p_00001: frequency=2, monetary=9.99, recency_days=0
#   p_00002: frequency=1, monetary=0.00, recency_days=1


RFM_EVENTS = [
    # p_00001 – session s1
    make_event(event_id="e1", player_id="p_00001", cohort="whale",
               session_id="s1", event_type="session_start",
               event_time=datetime(2024, 1, 1, 9, 0), days_since_install=0),
    make_event(event_id="e2", player_id="p_00001", cohort="whale",
               session_id="s1", event_type="purchase", amount_usd=9.99,
               event_time=datetime(2024, 1, 1, 9, 30), days_since_install=0),
    # p_00001 – session s2
    make_event(event_id="e3", player_id="p_00001", cohort="whale",
               session_id="s2", event_type="session_start",
               event_time=datetime(2024, 1, 2, 10, 0), days_since_install=1),
    # p_00002 – session s3
    make_event(event_id="e4", player_id="p_00002", cohort="f2p",
               session_id="s3", event_type="session_start",
               event_time=datetime(2024, 1, 1, 8, 0), days_since_install=0),
]


@pytest.fixture()
def rfm():
    return aggregate_rfm(make_df(RFM_EVENTS))


class TestAggregateRFM:
    def test_one_row_per_player(self, rfm):
        assert len(rfm) == 2

    def test_frequency_multi_session_player(self, rfm):
        row = rfm[rfm["player_id"] == "p_00001"].iloc[0]
        assert row["frequency"] == 2

    def test_frequency_single_session_player(self, rfm):
        row = rfm[rfm["player_id"] == "p_00002"].iloc[0]
        assert row["frequency"] == 1

    def test_monetary_spender(self, rfm):
        row = rfm[rfm["player_id"] == "p_00001"].iloc[0]
        assert row["monetary"] == pytest.approx(9.99)

    def test_monetary_non_spender_is_zero(self, rfm):
        row = rfm[rfm["player_id"] == "p_00002"].iloc[0]
        assert row["monetary"] == 0.0

    def test_recency_most_recent_player_is_zero(self, rfm):
        # p_00001 last seen = reference_date → recency = 0
        row = rfm[rfm["player_id"] == "p_00001"].iloc[0]
        assert row["recency_days"] == 0

    def test_recency_older_player(self, rfm):
        # p_00002 last seen 2024-01-01 08:00, reference 2024-01-02 10:00 → 1 day
        row = rfm[rfm["player_id"] == "p_00002"].iloc[0]
        assert row["recency_days"] == 1

    def test_first_seen(self, rfm):
        row = rfm[rfm["player_id"] == "p_00001"].iloc[0]
        assert row["first_seen"] == pd.Timestamp("2024-01-01 09:00:00")

    def test_last_seen(self, rfm):
        row = rfm[rfm["player_id"] == "p_00001"].iloc[0]
        assert row["last_seen"] == pd.Timestamp("2024-01-02 10:00:00")

    def test_cohort_preserved(self, rfm):
        row = rfm[rfm["player_id"] == "p_00001"].iloc[0]
        assert row["cohort"] == "whale"



# aggregate_sessions()

#
# Session s1: session_start + 2×level_complete + 1×ad_watched + purchase $4.99


SESSION_EVENTS = [
    make_event(event_id="e1", session_id="s1", event_type="session_start",
               event_time=datetime(2024, 1, 1, 9, 0)),
    make_event(event_id="e2", session_id="s1", event_type="level_complete",
               level_id=1, event_time=datetime(2024, 1, 1, 9, 5)),
    make_event(event_id="e3", session_id="s1", event_type="ad_watched",
               event_time=datetime(2024, 1, 1, 9, 6)),
    make_event(event_id="e4", session_id="s1", event_type="level_complete",
               level_id=2, event_time=datetime(2024, 1, 1, 9, 10)),
    make_event(event_id="e5", session_id="s1", event_type="purchase",
               amount_usd=4.99, event_time=datetime(2024, 1, 1, 9, 15)),
]


@pytest.fixture()
def sessions():
    return aggregate_sessions(make_df(SESSION_EVENTS))


class TestAggregateSessions:
    def test_one_row_per_session(self, sessions):
        assert len(sessions) == 1

    def test_levels_completed(self, sessions):
        assert sessions.iloc[0]["levels_completed"] == 2

    def test_ads_watched(self, sessions):
        assert sessions.iloc[0]["ads_watched"] == 1

    def test_revenue(self, sessions):
        assert sessions.iloc[0]["revenue"] == pytest.approx(4.99)

    def test_session_start_time(self, sessions):
        assert sessions.iloc[0]["session_start"] == pd.Timestamp("2024-01-01 09:00:00")

    def test_session_with_no_purchase_has_zero_revenue(self):
        events = [
            make_event(event_id="e1", session_id="s2", event_type="session_start",
                       event_time=datetime(2024, 1, 1, 10, 0)),
            make_event(event_id="e2", session_id="s2", event_type="level_complete",
                       level_id=1, event_time=datetime(2024, 1, 1, 10, 5)),
        ]
        result = aggregate_sessions(make_df(events))
        assert result.iloc[0]["revenue"] == 0.0

    def test_multiple_sessions_are_independent(self):
        events = [
            make_event(event_id="e1", session_id="sA", event_type="session_start",
                       event_time=datetime(2024, 1, 1, 9, 0)),
            make_event(event_id="e2", session_id="sA", event_type="purchase",
                       amount_usd=0.99, event_time=datetime(2024, 1, 1, 9, 5)),
            make_event(event_id="e3", session_id="sB", event_type="session_start",
                       event_time=datetime(2024, 1, 1, 10, 0)),
            make_event(event_id="e4", session_id="sB", event_type="purchase",
                       amount_usd=19.99, event_time=datetime(2024, 1, 1, 10, 5)),
        ]
        result = aggregate_sessions(make_df(events))
        assert len(result) == 2
        rev_by_session = result.set_index("session_id")["revenue"]
        assert rev_by_session["sA"] == pytest.approx(0.99)
        assert rev_by_session["sB"] == pytest.approx(19.99)
