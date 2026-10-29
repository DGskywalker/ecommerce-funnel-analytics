import numpy as np
import pandas as pd
import pytest

from funnel_analytics import metrics as m
from funnel_analytics.config import DATASETS

GA4 = DATASETS["demo"]


def mart(rows):
    cols = ["channel", "device", "region", "visitor_type", "sessions", "open_view", "open_cart",
            "open_checkout", "open_purchase", "closed_view", "closed_cart", "closed_checkout",
            "closed_purchase", "transactions", "revenue", "pageviews", "engagement_sec"]
    return pd.DataFrame(rows, columns=cols)


@pytest.fixture
def two_devices():
    return mart([
        ["Direct", "Desktop", "US", "New", 1000, 500, 200, 100, 50, 500, 200, 100, 50, 50, 5000.0, 4000, 1e5],
        ["Direct", "Mobile", "US", "New", 1000, 400, 120, 60, 12, 400, 120, 60, 12, 12, 720.0, 3000, 8e4],
    ])


def test_wilson_interval_contains_point_and_is_bounded():
    lo, hi = m.wilson_ci(np.array([0, 5, 100]), np.array([10, 100, 100]))
    assert np.all(lo >= 0) and np.all(hi <= 1)
    assert lo[1] < 0.05 < hi[1]
    assert hi[2] == pytest.approx(1.0)


def test_benjamini_hochberg_matches_reference():
    # statsmodels.stats.multitest.multipletests(..., method="fdr_bh") reference values
    p = np.array([0.01, 0.04, 0.03, 0.005])
    np.testing.assert_allclose(m.benjamini_hochberg(p), [0.02, 0.04, 0.04, 0.02])


def test_funnel_table_is_monotonic_and_rates_chain(two_devices):
    ft = m.funnel_table(two_devices, GA4, "closed")
    assert list(ft["step"]) == ["visit", "view", "cart", "checkout", "purchase"]
    assert ft["sessions"].is_monotonic_decreasing
    # Product of step rates equals the overall closed conversion.
    assert np.prod(ft["step_conversion"].iloc[1:]) == pytest.approx(62 / 2000)


def test_unobserved_steps_are_skipped():
    uci = DATASETS["uci"]
    df = mart([["T1", "OS 1", "R1", "New", 100, 90, None, 30, 10, 90, None, 30, 10, 10, None, 900, 1.0]])
    ft = m.funnel_table(df, uci)
    assert "cart" not in set(ft["step"])
    assert ft.loc[ft["step"] == "checkout", "step_conversion"].item() == pytest.approx(30 / 90)


def test_segment_table_flags_significant_gap(two_devices):
    seg = m.segment_table(two_devices, "device", GA4)
    desk = seg.set_index("device").loc["Desktop"]
    assert desk["conversion_rate"] == pytest.approx(0.05)
    assert desk["significant"]
    assert desk["aov"] == pytest.approx(100.0)


def test_opportunity_sizing_closes_gap_to_overall(two_devices):
    opps = m.opportunities(two_devices, GA4, dims=("device",), min_sessions=0)
    mob = opps[(opps.segment == "Mobile") & (opps.step == "purchase")].iloc[0]
    overall_rate = 62 / 160
    assert mob["benchmark"] == pytest.approx(overall_rate)
    assert mob["extra_purchases"] == pytest.approx(60 * (overall_rate - 0.2))
    assert (opps["extra_purchases"] > 0).all()


def test_what_if_propagates_downstream(two_devices):
    res = m.what_if(two_devices, GA4, "cart", 0.10)
    assert res["extra_purchases"] == pytest.approx(62 * 0.10)
