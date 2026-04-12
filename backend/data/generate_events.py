"""
Generate synthetic GemBlast player event data.

Produces 5 000 players over 180 days with power-law retention and three
spend cohorts (whale / mid / f2p).

Usage:
    python backend/data/generate_events.py

Output:
    backend/data/raw/player_events.csv
"""

import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Configuration

RANDOM_SEED = 42
N_PLAYERS = 5_000
SIM_DAYS = 180
SIM_START = datetime(2024, 1, 1)

# Spread installs across the first 150 days so every player has
# at least 30 days of potential activity before the window closes.
INSTALL_WINDOW_DAYS = 150

# IAP price points and sampling weights per cohort
IAP_PRICES: dict[str, list[float]] = {
    "whale": [0.99, 4.99, 9.99, 19.99, 49.99, 99.99],
    "mid":   [0.99, 4.99, 9.99, 19.99],
    "f2p":   [0.99],
}
IAP_WEIGHTS: dict[str, list[float]] = {
    "whale": [0.05, 0.15, 0.25, 0.30, 0.15, 0.10],
    "mid":   [0.30, 0.35, 0.25, 0.10],
    "f2p":   [1.00],
}

# Cohort parameters
# ret_base  : P(active on day 1 post-install)
# ret_alpha : power-law exponent — higher = faster churn
# sess_lambda   : Poisson mean for sessions per active day
# levels_lambda : Poisson mean for levels completed per session
# purchase_prob : P(at least one IAP in a session)
# ad_prob       : P(ad watched after each level completion
COHORTS: dict[str, dict] = {
    "whale": {
        "share":          0.05,
        "ret_base":       0.95,
        "ret_alpha":      0.25,
        "sess_lambda":    3.5,
        "levels_lambda":  6.0,
        "purchase_prob":  0.15,
        "ad_prob":        0.05,
    },
    "mid": {
        "share":          0.20,
        "ret_base":       0.88,
        "ret_alpha":      0.45,
        "sess_lambda":    2.0,
        "levels_lambda":  4.0,
        "purchase_prob":  0.04,
        "ad_prob":        0.35,
    },
    "f2p": {
        "share":          0.75,
        "ret_base":       0.75,
        "ret_alpha":      0.70,
        "sess_lambda":    1.2,
        "levels_lambda":  2.5,
        "purchase_prob":  0.005,
        "ad_prob":        0.65,
    },
}

OUT_PATH = Path(__file__).parent / "raw" / "player_events.csv"

# Core helpers

def retention_prob(day: int, base: float, alpha: float) -> float:
    """
    P(player opens the game on `day` days after install).

    Uses a power-law decay:  P = base * (day + 1)^(-alpha)
    Day 0 (install day) always returns 1.0.

    Approximate day-1 / day-7 / day-30 values:
        whale : 80 % / 57 % / 40 %
        mid   : 64 % / 36 % / 22 %
        f2p   : 46 % / 17 % /  8 %
    """
    if day == 0:
        return 1.0
    return min(1.0, base * (day + 1) ** (-alpha))


def sample_iap(cohort: str) -> float:
    return random.choices(IAP_PRICES[cohort], weights=IAP_WEIGHTS[cohort], k=1)[0]


# Event generation

def generate_session_events(
    session_id: str,
    session_time: datetime,
    cohort: str,
    player_level: int,
    cfg: dict,
) -> tuple[list[dict], int]:
    """
    Build all events for one session.

    Event order within a session:
        session_start → [level_complete → maybe ad_watched] × N → maybe purchase

    Returns the event list and the updated cumulative player level.
    """
    events: list[dict] = []
    t = session_time

    # session_start
    events.append({
        "event_type": "session_start",
        "event_time": t,
        "session_id": session_id,
        "level_id":   None,
        "amount_usd": None,
    })
    t += timedelta(seconds=random.randint(5, 30))

    # levels (+ optional ads between levels)
    n_levels = max(1, int(np.random.poisson(cfg["levels_lambda"])))
    for _ in range(n_levels):
        player_level += 1
        events.append({
            "event_type": "level_complete",
            "event_time": t,
            "session_id": session_id,
            "level_id":   player_level,
            "amount_usd": None,
        })
        t += timedelta(seconds=random.randint(60, 300))

        if random.random() < cfg["ad_prob"]:
            events.append({
                "event_type": "ad_watched",
                "event_time": t,
                "session_id": session_id,
                "level_id":   None,
                "amount_usd": None,
            })
            t += timedelta(seconds=random.randint(15, 30))

    # optional purchase at end of session
    if random.random() < cfg["purchase_prob"]:
        events.append({
            "event_type": "purchase",
            "event_time": t,
            "session_id": session_id,
            "level_id":   None,
            "amount_usd": sample_iap(cohort),
        })

    return events, player_level


def generate_player(player_id: str, cohort: str, install_day: int) -> list[dict]:
    """Return all event rows for a single player."""
    cfg = COHORTS[cohort]
    install_date = SIM_START + timedelta(days=install_day)
    rows: list[dict] = []
    player_level = 0

    days_available = SIM_DAYS - install_day

    for d in range(days_available):
        if random.random() > retention_prob(d, cfg["ret_base"], cfg["ret_alpha"]):
            continue

        n_sessions = max(1, int(np.random.poisson(cfg["sess_lambda"])))
        n_sessions = min(n_sessions, 20)  # guard against Poisson outliers

        # Spread sessions across random minutes of the day (with replacement
        # so two sessions can technically start in the same minute).
        session_minutes = sorted(random.choices(range(1440), k=n_sessions))

        for minute in session_minutes:
            session_time = install_date + timedelta(days=d, minutes=minute)
            session_id = str(uuid.uuid4())

            events, player_level = generate_session_events(
                session_id, session_time, cohort, player_level, cfg
            )

            for ev in events:
                rows.append({
                    "event_id":           str(uuid.uuid4()),
                    "player_id":          player_id,
                    "cohort":             cohort,
                    "install_date":       install_date.date(),
                    "days_since_install": d,
                    **ev,
                })

    return rows


# Main

def main() -> None:
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)

    cohort_names = list(COHORTS.keys())
    cohort_weights = [COHORTS[c]["share"] for c in cohort_names]

    print(f"Generating {N_PLAYERS:,} players over {SIM_DAYS} days...")

    all_rows: list[dict] = []
    for i in range(N_PLAYERS):
        player_id = f"p_{i + 1:05d}"
        cohort = random.choices(cohort_names, weights=cohort_weights, k=1)[0]
        install_day = random.randint(0, INSTALL_WINDOW_DAYS - 1)

        all_rows.extend(generate_player(player_id, cohort, install_day))

        if (i + 1) % 500 == 0:
            print(f"  {i + 1:,}/{N_PLAYERS:,} players  |  {len(all_rows):,} events so far")

    # Build DataFrame
    df = pd.DataFrame(all_rows)
    df["event_time"] = pd.to_datetime(df["event_time"])
    df["install_date"] = pd.to_datetime(df["install_date"]).dt.date
    df = df.sort_values("event_time").reset_index(drop=True)

    # Save
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)

    # Summary
    print(f"\nSaved {len(df):,} events -> {OUT_PATH}\n")
    print("-- Players per cohort --------------------------")
    cohort_players = df.groupby("cohort")["player_id"].nunique().rename("players")
    print(cohort_players.to_string())

    print("\n-- Events per type -----------------------------")
    print(df["event_type"].value_counts().to_string())

    print("\n-- Revenue by cohort ---------------------------")
    rev = (
        df[df["event_type"] == "purchase"]
        .groupby("cohort")["amount_usd"]
        .agg(transactions="count", revenue="sum")
    )
    print(rev.to_string())

    total_rev = df["amount_usd"].sum()
    print(f"\nTotal revenue : ${total_rev:,.2f}")
    print(f"Date range    : {df['event_time'].min().date()} -> {df['event_time'].max().date()}")
    print(f"Unique players: {df['player_id'].nunique():,}")


if __name__ == "__main__":
    main()
