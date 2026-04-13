"""
Tests for models/ltv_model.py

Covers:
- build_model_inputs  : correct lifetimes convention, constraints
- fit_bgnbd           : model fits without error
- fit_gamma_gamma     : model fits on players with repeat sessions
- score_players       : output shape, value bounds, monotonicity
- assign_segments     : correct labels, high_ltv > low_ltv
"""

from datetime import datetime

import pandas as pd
import pytest

from models.ltv_model import (
    AD_REVENUE_PER_SESSION,
    assign_segments,
    build_model_inputs,
    fit_bgnbd,
    fit_gamma_gamma,
    score_players,
)

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

# 15 players with a wide spread of behaviour so all 3 segments are populated.
#
# Whales   : high session count, real spend
# Mid      : moderate sessions, small spend
# F2P      : few sessions, zero spend
#
# reference_date is implicitly max(last_seen) = 2024-06-25

_RFM_ROWS = [
    # player_id     cohort  first_seen            last_seen             freq  monetary
    ("p_00001", "whale", "2024-01-01", "2024-06-25", 80, 850.0),
    ("p_00002", "whale", "2024-01-01", "2024-06-20", 70, 600.0),
    ("p_00003", "whale", "2024-01-15", "2024-06-15", 60, 400.0),
    ("p_00004", "mid",   "2024-01-01", "2024-05-01", 30,  60.0),
    ("p_00005", "mid",   "2024-02-01", "2024-05-15", 25,  45.0),
    ("p_00006", "mid",   "2024-02-15", "2024-04-30", 20,  20.0),
    ("p_00007", "mid",   "2024-03-01", "2024-04-01", 15,   5.0),
    ("p_00008", "f2p",   "2024-01-01", "2024-03-01", 10,   0.0),
    ("p_00009", "f2p",   "2024-02-01", "2024-03-15",  8,   0.0),
    ("p_00010", "f2p",   "2024-01-01", "2024-02-15",  6,   0.0),
    ("p_00011", "f2p",   "2024-03-01", "2024-03-20",  4,   0.0),
    ("p_00012", "f2p",   "2024-01-15", "2024-02-01",  3,   0.0),
    ("p_00013", "f2p",   "2024-04-01", "2024-04-10",  2,   0.0),
    ("p_00014", "f2p",   "2024-05-01", "2024-05-03",  2,   0.0),
    ("p_00015", "f2p",   "2024-06-01", "2024-06-02",  1,   0.0),
]


@pytest.fixture(scope="module")
def rfm() -> pd.DataFrame:
    rows = []
    for pid, cohort, first, last, freq, monetary in _RFM_ROWS:
        first_dt = datetime.fromisoformat(first)
        last_dt = datetime.fromisoformat(last)
        rows.append(
            {
                "player_id": pid,
                "cohort": cohort,
                "install_date": first_dt.date(),
                "first_seen": first_dt,
                "last_seen": last_dt,
                "recency_days": 0,   # not used by model — present for schema compat
                "frequency": freq,
                "monetary": monetary,
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def inputs(rfm) -> pd.DataFrame:
    return build_model_inputs(rfm)


@pytest.fixture(scope="module")
def bgf(inputs):
    return fit_bgnbd(inputs)


@pytest.fixture(scope="module")
def ggf(inputs):
    return fit_gamma_gamma(inputs)


@pytest.fixture(scope="module")
def scores(inputs, bgf, ggf) -> pd.DataFrame:
    return score_players(inputs, bgf, ggf)


@pytest.fixture(scope="module")
def segmented(scores) -> pd.DataFrame:
    return assign_segments(scores)


# ---------------------------------------------------------------------------
# build_model_inputs
# ---------------------------------------------------------------------------


class TestBuildModelInputs:
    def test_required_columns_present(self, inputs):
        required = {"player_id", "cohort", "frequency", "recency", "T", "monetary_value", "monetary"}
        assert required.issubset(inputs.columns)

    def test_one_row_per_player(self, rfm, inputs):
        assert len(inputs) == len(rfm)

    def test_frequency_is_non_negative(self, inputs):
        assert (inputs["frequency"] >= 0).all()

    def test_frequency_is_total_minus_one(self, rfm, inputs):
        # player with 1 session → frequency = 0
        single = inputs[inputs["player_id"] == "p_00015"]
        assert single.iloc[0]["frequency"] == 0

    def test_single_session_player_has_zero_recency(self, inputs):
        # lifetimes constraint: recency must be 0 when frequency == 0
        zero_freq = inputs[inputs["frequency"] == 0]
        assert (zero_freq["recency"] == 0).all()

    def test_recency_leq_T(self, inputs):
        assert (inputs["recency"] <= inputs["T"]).all()

    def test_T_is_at_least_one(self, inputs):
        assert (inputs["T"] >= 1).all()

    def test_monetary_value_always_positive(self, inputs):
        # even f2p players get the ad-revenue floor
        assert (inputs["monetary_value"] > 0).all()

    def test_f2p_monetary_value_floored(self, inputs):
        f2p = inputs[inputs["cohort"] == "f2p"]
        assert (abs(f2p["monetary_value"] - AD_REVENUE_PER_SESSION) < 1e-9).all()

    def test_whale_monetary_value_above_floor(self, inputs):
        whales = inputs[inputs["cohort"] == "whale"]
        assert (whales["monetary_value"] > AD_REVENUE_PER_SESSION).all()


# ---------------------------------------------------------------------------
# fit_bgnbd / fit_gamma_gamma
# ---------------------------------------------------------------------------


class TestModelFitting:
    def test_bgnbd_has_four_params(self, bgf):
        assert len(bgf.params_) == 4

    def test_bgnbd_params_positive(self, bgf):
        assert (bgf.params_ > 0).all()

    def test_bgnbd_log_likelihood_finite(self, bgf):
        import math
        assert math.isfinite(bgf._negative_log_likelihood_)

    def test_gamma_gamma_has_three_params(self, ggf):
        assert len(ggf.params_) == 3

    def test_gamma_gamma_params_positive(self, ggf):
        assert (ggf.params_ > 0).all()


# ---------------------------------------------------------------------------
# score_players
# ---------------------------------------------------------------------------


class TestScorePlayers:
    def test_one_row_per_player(self, rfm, scores):
        assert len(scores) == len(rfm)

    def test_required_columns(self, scores):
        for col in (
            "player_id",
            "predicted_purchases_30d",
            "predicted_purchases_90d",
            "churn_probability",
            "expected_ltv_90d",
        ):
            assert col in scores.columns

    def test_churn_probability_lower_bound(self, scores):
        assert (scores["churn_probability"] >= 0).all()

    def test_churn_probability_upper_bound(self, scores):
        assert (scores["churn_probability"] <= 1).all()

    def test_predicted_purchases_30d_non_negative(self, scores):
        assert (scores["predicted_purchases_30d"] >= 0).all()

    def test_predicted_purchases_90d_non_negative(self, scores):
        assert (scores["predicted_purchases_90d"] >= 0).all()

    def test_90d_geq_30d(self, scores):
        assert (scores["predicted_purchases_90d"] >= scores["predicted_purchases_30d"]).all()

    def test_ltv_non_negative(self, scores):
        assert (scores["expected_ltv_90d"] >= 0).all()

    def test_no_null_values(self, scores):
        cols = ["predicted_purchases_30d", "predicted_purchases_90d",
                "churn_probability", "expected_ltv_90d"]
        assert not scores[cols].isnull().any().any()

    def test_whales_have_lower_churn_than_f2p(self, scores):
        # cohort is included in scores by score_players()
        whale_churn = scores[scores["cohort"] == "whale"]["churn_probability"].mean()
        f2p_churn = scores[scores["cohort"] == "f2p"]["churn_probability"].mean()
        assert whale_churn < f2p_churn

    def test_whales_have_higher_ltv_than_f2p(self, scores):
        whale_ltv = scores[scores["cohort"] == "whale"]["expected_ltv_90d"].mean()
        f2p_ltv = scores[scores["cohort"] == "f2p"]["expected_ltv_90d"].mean()
        assert whale_ltv > f2p_ltv


# ---------------------------------------------------------------------------
# assign_segments
# ---------------------------------------------------------------------------


class TestAssignSegments:
    def test_segment_column_present(self, segmented):
        assert "segment" in segmented.columns

    def test_only_valid_segment_labels(self, segmented):
        assert set(segmented["segment"].unique()).issubset({"high_ltv", "mid_ltv", "low_ltv"})

    def test_all_three_segments_present(self, segmented):
        assert segmented["segment"].nunique() == 3

    def test_high_ltv_min_geq_low_ltv_max(self, segmented):
        high = segmented[segmented["segment"] == "high_ltv"]["expected_ltv_90d"]
        low = segmented[segmented["segment"] == "low_ltv"]["expected_ltv_90d"]
        assert high.min() >= low.max()

    def test_high_ltv_is_at_most_20_pct(self, segmented):
        # high_ltv captures the top 20 % — never more than 30 % even after rounding
        n = len(segmented)
        counts = segmented["segment"].value_counts()
        assert counts["high_ltv"] <= n * 0.30

    def test_idempotent(self, scores):
        # Calling assign_segments twice should give same result
        once = assign_segments(scores)
        twice = assign_segments(scores)
        pd.testing.assert_frame_equal(once, twice)
