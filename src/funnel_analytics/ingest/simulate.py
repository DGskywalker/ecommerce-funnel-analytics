"""Simulated sessions in the exact column layout of the BigQuery GA4 export.

These rows exist so the GA4 pipeline and dashboard run before anyone exports
the real sample. They are labelled SIMULATED everywhere they appear. The effect
sizes are made up, chosen to look like a typical merchandise store
(Nov 2020 – Jan 2021: Black Friday, Cyber Monday, the pre-Christmas peak and a
January lull).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

START, END = "2020-11-01", "2021-01-31"

# channel: (share, source, medium, view, cart, checkout, purchase) logit effects
CHANNELS = {
    "Organic Search": (0.33, "google", "organic", 0.00, 0.00, 0.00, 0.00),
    "Direct": (0.24, "(direct)", "(none)", 0.10, 0.15, 0.05, 0.10),
    "Referral": (0.15, "youtube.com", "referral", -0.35, -0.20, 0.00, -0.05),
    "Paid Search": (0.09, "google", "cpc", 0.35, -0.15, -0.10, -0.35),
    "Organic Social": (0.04, "facebook.com", "social", -0.60, -0.45, 0.00, -0.10),
    "Email": (0.03, "newsletter", "email", 0.55, 0.45, 0.10, 0.25),
    "Obfuscated": (0.12, "<Other>", "<Other>", 0.00, 0.00, 0.00, 0.00),
}
# device: (share, view, cart, checkout, purchase, mean order value)
DEVICES = {
    "desktop": (0.58, 0.00, 0.00, 0.00, 0.00, 88.0),
    "mobile": (0.39, -0.15, -0.25, -0.20, -0.95, 64.0),
    "tablet": (0.03, -0.05, -0.10, -0.10, -0.40, 75.0),
}
COUNTRIES = {
    "United States": 0.42, "India": 0.09, "Canada": 0.08, "United Kingdom": 0.05,
    "France": 0.03, "Spain": 0.03, "Germany": 0.03, "Taiwan": 0.025, "Japan": 0.02,
    "Singapore": 0.02, "Australia": 0.02, "Italy": 0.015, "(not set)": 0.02,
}
BASE = {"view": 0.42, "cart": 0.22, "checkout": 0.50, "purchase": 0.50}


def _logit(p: float) -> float:
    return float(np.log(p / (1 - p)))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-x))


def _daily_weights(days: pd.DatetimeIndex) -> np.ndarray:
    w = np.ones(len(days))
    w[days.dayofweek >= 5] *= 0.8
    for d, boost in {"2020-11-27": 2.2, "2020-11-30": 1.9, "2020-11-28": 1.5, "2020-11-29": 1.4}.items():
        w[days == pd.Timestamp(d)] *= boost
    december = (days >= "2020-12-01") & (days <= "2020-12-18")
    w[december] *= np.linspace(1.15, 1.6, december.sum())
    w[(days > "2020-12-18") & (days <= "2020-12-31")] *= 0.85
    w[days >= "2021-01-01"] *= 0.7
    return w / w.sum()


def _season_purchase_effect(dates: pd.DatetimeIndex) -> np.ndarray:
    eff = np.zeros(len(dates))
    eff[dates.isin(pd.to_datetime(["2020-11-27", "2020-11-30"]))] += 0.35
    # After the shipping cutoff people still browse but stop buying.
    eff[(dates > "2020-12-18") & (dates <= "2020-12-31")] -= 0.45
    return eff


def generate(n_sessions: int = 90_000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.date_range(START, END, freq="D")
    dates = pd.DatetimeIndex(rng.choice(days, size=n_sessions, p=_daily_weights(days)))

    ch_names = list(CHANNELS)
    ch = rng.choice(len(ch_names), size=n_sessions, p=[CHANNELS[c][0] for c in ch_names])
    ch_eff = np.array([CHANNELS[c][3:] for c in ch_names])[ch]

    dev_names = list(DEVICES)
    dev = rng.choice(len(dev_names), size=n_sessions, p=[DEVICES[d][0] for d in dev_names])
    dev_eff = np.array([DEVICES[d][1:5] for d in dev_names])[dev]
    aov = np.array([DEVICES[d][5] for d in dev_names])[dev]

    c_names = list(COUNTRIES)
    c_p = np.array(list(COUNTRIES.values()))
    country = np.array(c_names)[rng.choice(len(c_names), size=n_sessions, p=c_p / c_p.sum())]
    us_eff = np.where(country == "United States", 0.15, 0.0)

    returning = rng.random(n_sessions) < 0.30
    session_number = np.where(returning, 2 + rng.geometric(0.45, n_sessions), 1)
    ret_eff = np.where(returning, 1.0, 0.0)

    def step(name: str, col: int, extra: np.ndarray) -> np.ndarray:
        x = _logit(BASE[name]) + ch_eff[:, col] + dev_eff[:, col] + extra
        return rng.random(n_sessions) < _sigmoid(x)

    view = step("view", 0, 0.2 * ret_eff)
    cart = view & step("cart", 1, 0.5 * ret_eff + us_eff)
    checkout = cart & step("checkout", 2, 0.15 * ret_eff)
    purchase = checkout & step("purchase", 3, 0.4 * ret_eff + _season_purchase_effect(dates))

    # GA4 tagging gaps: some sessions skip an event they must logically have fired.
    view_logged = view & ~(purchase & (rng.random(n_sessions) < 0.05))
    cart_logged = cart & ~(checkout & (rng.random(n_sessions) < 0.08))

    transactions = np.where(purchase, 1 + (rng.random(n_sessions) < 0.04), 0)
    revenue = np.where(
        purchase,
        np.round(rng.lognormal(np.log(aov) - 0.18, 0.6, n_sessions) * transactions, 2),
        0.0,
    )
    # A slice of purchases arrives without a value (as in the obfuscated sample).
    revenue[purchase & (rng.random(n_sessions) < 0.02)] = 0.0

    depth = view.astype(int) + cart + checkout + purchase
    pageviews = 1 + depth * 2 + rng.poisson(1.5 + depth, n_sessions)
    engagement = np.round(rng.gamma(1.6 + depth, 25.0, n_sessions), 1)

    src = np.array([CHANNELS[c][1] for c in ch_names], dtype=object)[ch]
    med = np.array([CHANNELS[c][2] for c in ch_names], dtype=object)[ch]
    # ~15% of sessions carry no session-level source/medium, so the user-scope fallback is used.
    no_session_src = rng.random(n_sessions) < 0.15

    return pd.DataFrame(
        {
            "session_id": [f"demo-{i:07d}" for i in range(n_sessions)],
            "session_date": dates.date,
            "ga_session_number": session_number,
            "session_source": np.where(no_session_src, None, src),
            "session_medium": np.where(no_session_src, None, med),
            "user_source": src,
            "user_medium": med,
            "device_category": np.array(dev_names)[dev],
            "country": country,
            "pageviews": pageviews,
            "engagement_sec": engagement,
            "has_view_item": view_logged,
            "has_add_to_cart": cart_logged,
            "has_begin_checkout": checkout,
            "has_purchase": purchase,
            "transactions": transactions,
            "purchase_revenue_usd": revenue,
        }
    ).sort_values(["session_date", "session_id"], ignore_index=True)


def load_raw(con, n_sessions: int = 90_000, seed: int = 7) -> int:
    df = generate(n_sessions, seed)
    con.register("demo_df", df)
    con.execute("CREATE OR REPLACE TABLE raw_demo AS SELECT * FROM demo_df")
    con.unregister("demo_df")
    return len(df)
