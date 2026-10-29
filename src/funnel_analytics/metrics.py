"""Funnel, segment, revenue and opportunity metrics computed on mart_funnel rows.

Every function takes the (already filtered) mart dataframe plus the DatasetSpec,
so the dashboard, write-up generator and tests all share one implementation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .config import STEPS, DatasetSpec


# --------------------------------------------------------------------------- #
# Statistics helpers
# --------------------------------------------------------------------------- #
def wilson_ci(k, n, z: float = 1.96):
    """Wilson score interval for a binomial proportion (vectorised, safe at n = 0)."""
    k = np.asarray(k, dtype=float)
    n = np.asarray(n, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = np.where(n > 0, k / n, np.nan)
        denom = 1 + z**2 / n
        centre = (p + z**2 / (2 * n)) / denom
        half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return np.clip(centre - half, 0, 1), np.clip(centre + half, 0, 1)


def two_proportion_z(k1, n1, k2, n2):
    """Two-sided z-test p-value for p1 != p2 (pooled variance). Vectorised."""
    k1, n1, k2, n2 = (np.asarray(x, dtype=float) for x in (k1, n1, k2, n2))
    with np.errstate(divide="ignore", invalid="ignore"):
        p_pool = (k1 + k2) / (n1 + n2)
        se = np.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
        z = (k1 / n1 - k2 / n2) / se
    return np.where(np.isfinite(z), 2 * stats.norm.sf(np.abs(z)), 1.0)


def benjamini_hochberg(p_values) -> np.ndarray:
    """False-discovery-rate adjusted p-values (Benjamini–Hochberg step-up)."""
    p = np.asarray(p_values, dtype=float)
    n = len(p)
    if n == 0:
        return p
    order = np.argsort(p)
    ranked = p[order] * n / np.arange(1, n + 1)
    adjusted = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.clip(adjusted, 0, 1)
    return out


def safe_div(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(np.asarray(b, dtype=float) > 0, np.asarray(a, dtype=float) / b, np.nan)


# --------------------------------------------------------------------------- #
# Core funnel
# --------------------------------------------------------------------------- #
def step_column(step: str, mode: str) -> str:
    return "sessions" if step == "visit" else f"{mode}_{step}"


def step_counts(df: pd.DataFrame, spec: DatasetSpec, mode: str = "closed") -> pd.Series:
    return pd.Series(
        {s: float(df[step_column(s, mode)].sum()) for s in spec.observed_steps}, dtype=float
    )


def funnel_table(df: pd.DataFrame, spec: DatasetSpec, mode: str = "closed") -> pd.DataFrame:
    counts = step_counts(df, spec, mode)
    top = counts.iloc[0] if len(counts) else 0
    prev = counts.shift(1)
    lo, hi = wilson_ci(counts.values, prev.fillna(counts.iloc[0]).values)
    out = pd.DataFrame(
        {
            "step": counts.index,
            "label": [spec.label(s) for s in counts.index],
            "sessions": counts.values,
            "pct_of_sessions": safe_div(counts.values, top),
            "step_conversion": safe_div(counts.values, prev.values),
            "ci_low": lo,
            "ci_high": hi,
            "drop_off": (prev - counts).values,
        }
    )
    out.loc[0, ["step_conversion", "ci_low", "ci_high", "drop_off"]] = np.nan
    out["drop_off_rate"] = 1 - out["step_conversion"]
    return out


def kpis(df: pd.DataFrame, spec: DatasetSpec, mode: str = "closed") -> dict:
    counts = step_counts(df, spec, mode)
    sessions = counts.get("visit", 0.0)
    purchases = float(df["open_purchase"].sum())  # every purchase counts toward CR
    revenue = float(df["revenue"].sum()) if spec.has_revenue else np.nan
    transactions = float(df["transactions"].sum())
    out = {
        "sessions": sessions,
        "purchasing_sessions": purchases,
        "conversion_rate": safe_div(purchases, sessions).item(),
        "revenue": revenue,
        "transactions": transactions,
        "aov": safe_div(revenue, transactions).item() if spec.has_revenue else np.nan,
        "revenue_per_session": safe_div(revenue, sessions).item() if spec.has_revenue else np.nan,
        "pages_per_session": safe_div(df["pageviews"].sum(), sessions).item(),
    }
    if "cart" in counts and "purchase" in counts:
        out["cart_abandonment"] = 1 - safe_div(counts["purchase"], counts["cart"]).item()
    if "checkout" in counts and "purchase" in counts:
        out["checkout_abandonment"] = 1 - safe_div(counts["purchase"], counts["checkout"]).item()
    return out


# --------------------------------------------------------------------------- #
# Segments
# --------------------------------------------------------------------------- #
def _agg_by(df: pd.DataFrame, dims) -> pd.DataFrame:
    dims = [dims] if isinstance(dims, str) else list(dims)
    num = [
        c for c in df.columns
        if c not in dims and c != "month_sort"
        and pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])
    ]
    return df.groupby(dims, dropna=False, observed=True)[num].sum(min_count=1).reset_index()


def segment_table(
    df: pd.DataFrame, dim: str, spec: DatasetSpec, mode: str = "closed", min_sessions: int = 0
) -> pd.DataFrame:
    """Conversion per segment with Wilson CIs, lift and a BH-corrected test vs the rest."""
    g = _agg_by(df, dim)
    total_s, total_p = g["sessions"].sum(), g["open_purchase"].sum()
    g["share"] = g["sessions"] / total_s
    g["purchases"] = g["open_purchase"]
    g["conversion_rate"] = safe_div(g["purchases"], g["sessions"])
    g["ci_low"], g["ci_high"] = wilson_ci(g["purchases"], g["sessions"])
    rest_s, rest_p = total_s - g["sessions"], total_p - g["purchases"]
    g["cr_rest"] = safe_div(rest_p, rest_s)
    g["lift_vs_rest"] = safe_div(g["conversion_rate"], g["cr_rest"]) - 1
    g["p_value"] = two_proportion_z(g["purchases"], g["sessions"], rest_p, rest_s)
    g["p_adj"] = benjamini_hochberg(g["p_value"].values)
    g["significant"] = g["p_adj"] < 0.05
    if spec.has_revenue:
        g["revenue_share"] = safe_div(g["revenue"], g["revenue"].sum())
        g["aov"] = safe_div(g["revenue"], g["transactions"])
        g["revenue_per_session"] = safe_div(g["revenue"], g["sessions"])
    prev = "visit"
    for s in spec.observed_steps[1:]:
        g[f"cr_{s}"] = safe_div(g[step_column(s, mode)], g[step_column(prev, mode)])
        prev = s
    g = g[g["sessions"] >= min_sessions]
    return g.sort_values("sessions", ascending=False, ignore_index=True)


def chi_square_independence(df: pd.DataFrame, dim: str, min_sessions: int = 30) -> dict:
    """Is conversion independent of this dimension? Returns chi², dof, p and Cramér's V."""
    g = _agg_by(df, dim)
    g = g[g["sessions"] >= min_sessions]
    if len(g) < 2:
        return {"chi2": np.nan, "dof": 0, "p_value": np.nan, "cramers_v": np.nan}
    table = np.column_stack([g["open_purchase"], g["sessions"] - g["open_purchase"]])
    chi2, p, dof, _ = stats.chi2_contingency(table)
    v = np.sqrt(chi2 / table.sum())  # min(r, c) - 1 == 1 for a 2-column table
    return {"chi2": chi2, "dof": dof, "p_value": p, "cramers_v": v}


def step_rates_long(df: pd.DataFrame, dim: str, spec: DatasetSpec, mode: str = "closed",
                    min_sessions: int = 0) -> pd.DataFrame:
    g = segment_table(df, dim, spec, mode, min_sessions)
    rows = []
    prev = "visit"
    for s in spec.observed_steps[1:]:
        n = g[step_column(prev, mode)]
        k = g[step_column(s, mode)]
        lo, hi = wilson_ci(k, n)
        rows.append(pd.DataFrame({
            dim: g[dim], "step": s, "transition": f"{spec.label(prev)} → {spec.label(s)}",
            "entrants": n, "converted": k, "rate": safe_div(k, n), "ci_low": lo, "ci_high": hi,
        }))
        prev = s
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def cross_tab(df: pd.DataFrame, row: str, col: str, min_sessions: int = 30) -> pd.DataFrame:
    g = _agg_by(df, [row, col])
    g["conversion_rate"] = safe_div(g["open_purchase"], g["sessions"])
    g.loc[g["sessions"] < min_sessions, "conversion_rate"] = np.nan
    return g


# --------------------------------------------------------------------------- #
# Opportunity sizing
# --------------------------------------------------------------------------- #
def opportunities(
    df: pd.DataFrame,
    spec: DatasetSpec,
    dims=("channel", "device", "visitor_type"),
    mode: str = "closed",
    min_sessions: int = 500,
    benchmark: str = "overall",
) -> pd.DataFrame:
    """Size the gain from lifting each segment's weak step up to a benchmark rate.

    For segment s and transition j-1 → j:
        extra_step_j   = entrants_{s,j-1} × max(0, bench_j − rate_{s,j})
        extra_purchase = extra_step_j × (purchases_s / reached_{s,j})   # downstream rate
        extra_revenue  = extra_purchase × AOV_s
    The benchmark is the rate across all sessions ("overall") or the 75th
    percentile of segment rates ("p75").
    """
    overall = step_counts(df, spec, mode)
    steps = spec.observed_steps
    total_purch = overall[steps[-1]]
    total_rev = df["revenue"].sum() if spec.has_revenue else np.nan
    rows = []
    for dim in dims:
        g = _agg_by(df, dim)
        g = g[g["sessions"] >= min_sessions]
        if g.empty:
            continue
        aov = safe_div(g["revenue"], g["transactions"]) if spec.has_revenue else np.full(len(g), np.nan)
        purch = g[step_column(steps[-1], mode)].to_numpy(float)
        for prev, step in zip(steps[:-1], steps[1:]):
            n = g[step_column(prev, mode)].to_numpy(float)
            k = g[step_column(step, mode)].to_numpy(float)
            rate = safe_div(k, n)
            if benchmark == "p75":
                bench = np.nanpercentile(rate, 75)
            else:
                bench = safe_div(overall[step], overall[prev]).item()
            gap = np.clip(bench - rate, 0, None)
            extra_step = n * gap
            downstream = safe_div(purch, k) if step != steps[-1] else np.ones(len(g))
            extra_p = extra_step * np.nan_to_num(downstream)
            for i, seg in enumerate(g[dim]):
                rows.append({
                    "dimension": dim, "segment": seg, "step": step,
                    "transition": f"{spec.label(prev)} → {spec.label(step)}",
                    "sessions": g["sessions"].iloc[i], "entrants": n[i], "rate": rate[i],
                    "benchmark": bench, "gap_pts": gap[i], "extra_purchases": extra_p[i],
                    "extra_purchases_pct": extra_p[i] / total_purch if total_purch else np.nan,
                    "extra_revenue": extra_p[i] * aov[i] if spec.has_revenue else np.nan,
                    "extra_revenue_pct": (extra_p[i] * aov[i] / total_rev)
                    if spec.has_revenue and total_rev else np.nan,
                })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out[out["extra_purchases"] > 0].sort_values(
        "extra_purchases", ascending=False, ignore_index=True
    )


def what_if(df: pd.DataFrame, spec: DatasetSpec, step: str, uplift: float,
            mode: str = "closed") -> dict:
    """Relative uplift on one step's conversion, carried through to purchases and revenue."""
    counts = step_counts(df, spec, mode)
    steps = list(counts.index)
    rates = counts / counts.shift(1)
    new_rates = rates.copy()
    new_rates[step] = min(rates[step] * (1 + uplift), 1.0)
    new_counts = counts.copy()
    for i in range(1, len(steps)):
        new_counts.iloc[i] = new_counts.iloc[i - 1] * new_rates.iloc[i]
    base_p, new_p = counts.iloc[-1], new_counts.iloc[-1]
    rev = df["revenue"].sum() if spec.has_revenue else np.nan
    aov = rev / df["transactions"].sum() if spec.has_revenue and df["transactions"].sum() else np.nan
    return {
        "base_purchases": base_p, "new_purchases": new_p, "extra_purchases": new_p - base_p,
        "extra_revenue": (new_p - base_p) * aov if spec.has_revenue else np.nan,
        "base_counts": counts, "new_counts": new_counts,
    }


# --------------------------------------------------------------------------- #
# Trends
# --------------------------------------------------------------------------- #
def trend(df: pd.DataFrame, spec: DatasetSpec, grain: str = "day", window: int = 7) -> pd.DataFrame:
    """Sessions, CR and revenue over time, with a rolling CR and a z-score anomaly flag."""
    if spec.time_grain == "month" or grain == "month":
        key = ["month_sort", "month_label"]
        g = _agg_by(df, key).sort_values("month_sort")
        g = g.rename(columns={"month_label": "period"})
        window = 1
    else:
        d = df.copy()
        d["period"] = pd.to_datetime(d["session_date"])
        if grain == "week":
            d["period"] = d["period"].dt.to_period("W-SUN").dt.start_time
        g = _agg_by(d.drop(columns=["session_date", "month_label"], errors="ignore"), "period")
        g = g.sort_values("period")
    g["conversion_rate"] = safe_div(g["open_purchase"], g["sessions"])
    g["ci_low"], g["ci_high"] = wilson_ci(g["open_purchase"], g["sessions"])
    if spec.has_revenue:
        g["revenue_per_session"] = safe_div(g["revenue"], g["sessions"])
        g["aov"] = safe_div(g["revenue"], g["transactions"])
    w = max(window, 1)
    g["cr_rolling"] = (g["open_purchase"].rolling(w, min_periods=1).sum()
                       / g["sessions"].rolling(w, min_periods=1).sum())
    std = g["conversion_rate"].std(ddof=0)
    g["cr_z"] = (g["conversion_rate"] - g["conversion_rate"].mean()) / std if std else 0.0
    g["anomaly"] = g["cr_z"].abs() > 2
    return g.reset_index(drop=True)


def pareto(df: pd.DataFrame, dim: str, value: str = "revenue") -> pd.DataFrame:
    g = _agg_by(df, dim).sort_values(value, ascending=False, ignore_index=True)
    g["cum_share"] = g[value].cumsum() / g[value].sum()
    return g


__all__ = [
    "STEPS", "wilson_ci", "two_proportion_z", "benjamini_hochberg", "funnel_table", "kpis",
    "segment_table", "chi_square_independence", "step_rates_long", "cross_tab",
    "opportunities", "what_if", "trend", "pareto",
]
