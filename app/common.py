"""Shared state, theming, cached loaders and filters for the dashboard pages."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import duckdb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import plotly.io as pio  # noqa: E402
import streamlit as st  # noqa: E402

from funnel_analytics import model as fa_model  # noqa: E402
from funnel_analytics import pipeline, warehouse  # noqa: E402
from funnel_analytics.config import DATASETS, DIMENSIONS, WAREHOUSE_PATH, DatasetSpec  # noqa: E402

# --------------------------------------------------------------------------- #
# Palette (validated reference palette: categorical order is fixed, never cycled)
# --------------------------------------------------------------------------- #
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OTHER_GRAY = "#a3a29c"
ORDINAL_BLUE = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]
SEQUENTIAL_BLUE = [
    [0.0, "#cde2fb"], [0.25, "#86b6ef"], [0.5, "#3987e5"], [0.75, "#1c5cab"], [1.0, "#0d366b"],
]
DIVERGING = [[0.0, "#e34948"], [0.5, "#f0efec"], [1.0, "#2a78d6"]]
STATUS = {"pass": "#0ca30c", "warn": "#fab219", "info": "#2a78d6", "fail": "#d03b3b"}
INK, INK_2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0", "#fcfcfb"

pio.templates["funnel"] = go.layout.Template(
    layout=dict(
        font=dict(family="Inter, system-ui, sans-serif", size=13, color=INK_2),
        title=dict(font=dict(size=15, color=INK), x=0, xanchor="left"),
        colorway=SERIES,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        margin=dict(l=8, r=8, t=48, b=8),
        xaxis=dict(gridcolor=GRID, linecolor=GRID, zeroline=False, ticks="", automargin=True),
        yaxis=dict(gridcolor=GRID, linecolor=GRID, zeroline=False, ticks="", automargin=True),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                    font=dict(color=INK_2)),
        hoverlabel=dict(bgcolor="white", font=dict(color=INK, size=12), bordercolor=GRID),
        bargap=0.25,
    )
)
pio.templates.default = "funnel"


def show(fig: go.Figure, height: int | None = None, key: str | None = None) -> None:
    # Set explicitly: Streamlit swaps in its own default template when it renders.
    fig.update_layout(template="funnel", plot_bgcolor=SURFACE, paper_bgcolor=SURFACE)
    if height:
        fig.update_layout(height=height)
    st.plotly_chart(fig, use_container_width=True, theme=None, key=key,
                    config={"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]})


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #
def pct(x, d: int = 1) -> str:
    return "–" if x is None or pd.isna(x) else f"{x * 100:.{d}f}%"


def num(x) -> str:
    return "–" if x is None or pd.isna(x) else f"{x:,.0f}"


def money(x, d: int = 0) -> str:
    return "–" if x is None or pd.isna(x) else f"${x:,.{d}f}"


# --------------------------------------------------------------------------- #
# Data access
# --------------------------------------------------------------------------- #
@st.cache_resource(show_spinner="Building the warehouse (first run only)…")
def _warehouse_ready() -> bool:
    pipeline.ensure_warehouse(log=lambda *_: None)
    return True


def connect() -> duckdb.DuckDBPyConnection:
    _warehouse_ready()
    return duckdb.connect(str(WAREHOUSE_PATH), read_only=True)


@st.cache_data(show_spinner=False)
def available_datasets() -> list[str]:
    with connect() as con:
        present = {r[0] for r in con.execute("SELECT DISTINCT dataset FROM mart_funnel").fetchall()}
    return [k for k in ("ga4", "uci", "demo") if k in present]


@st.cache_data(show_spinner=False)
def load_mart(dataset: str) -> pd.DataFrame:
    with connect() as con:
        df = con.execute("SELECT * FROM mart_funnel WHERE dataset = ?", [dataset]).df()
    for c in DIMENSIONS:
        df[c] = df[c].astype(str)
    return df


@st.cache_data(show_spinner=False)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    with connect() as con:
        return con.execute(sql, list(params)).df()


@st.cache_data(show_spinner=False)
def quality_checks() -> pd.DataFrame:
    with connect() as con:
        return warehouse.run_quality_checks(con)


@st.cache_resource(show_spinner="Training propensity models…")
def train_model(dataset: str, include_outcome_proxies: bool):
    with connect() as con:
        return fa_model.train(con, dataset, include_outcome_proxies)


@st.cache_data(show_spinner=False)
def segment_order(dataset: str, dim: str) -> list[str]:
    """Stable order (by total sessions, unfiltered) so colours follow the entity, not the rank."""
    df = load_mart(dataset)
    return df.groupby(dim)["sessions"].sum().sort_values(ascending=False).index.tolist()


def color_map(dataset: str, dim: str, max_series: int = 7) -> dict[str, str]:
    order = segment_order(dataset, dim)
    cmap = {seg: SERIES[i] for i, seg in enumerate(order[:max_series])}
    cmap["Other"] = OTHER_GRAY
    return cmap


def fold_other(df: pd.DataFrame, dataset: str, dim: str, keep: int = 7) -> pd.DataFrame:
    top = set(segment_order(dataset, dim)[:keep])
    out = df.copy()
    out[dim] = out[dim].where(out[dim].isin(top), "Other")
    return out


# --------------------------------------------------------------------------- #
# Sidebar context
# --------------------------------------------------------------------------- #
@dataclass
class Ctx:
    dataset: str
    spec: DatasetSpec
    df: pd.DataFrame          # filtered mart
    full: pd.DataFrame        # unfiltered mart for the dataset
    mode: str                 # "closed" | "open"
    min_sessions: int
    filters_active: bool


def sidebar() -> Ctx:
    datasets = available_datasets()
    with st.sidebar:
        st.markdown("### Data")
        dataset = st.selectbox(
            "Dataset", datasets, format_func=lambda k: DATASETS[k].short, key="dataset",
            help="GA4 appears once you add a BigQuery export to data/raw/ga4/. See the README.",
        )
        spec = DATASETS[dataset]
        full = load_mart(dataset)
        df = full

        mode = st.radio(
            "Funnel type", ["closed", "open"], horizontal=True, key="mode",
            format_func=lambda m: m.title(),
            help="Closed: a step counts only if every earlier step happened in the same "
                 "session (GA4's default). Open: any session that fired the step counts.",
        )

        st.markdown("### Filters")
        if spec.time_grain == "day":
            dmin, dmax = pd.to_datetime(full["session_date"]).min(), pd.to_datetime(full["session_date"]).max()
            rng = st.date_input("Date range", (dmin.date(), dmax.date()), min_value=dmin.date(),
                                max_value=dmax.date(), key=f"dates_{dataset}")
            if isinstance(rng, (list, tuple)) and len(rng) == 2:
                d = pd.to_datetime(df["session_date"])
                df = df[(d >= pd.Timestamp(rng[0])) & (d <= pd.Timestamp(rng[1]))]
        else:
            months = (full[["month_sort", "month_label"]].drop_duplicates()
                      .sort_values("month_sort")["month_label"].tolist())
            sel = st.multiselect("Months", months, key=f"months_{dataset}",
                                 placeholder="All months")
            if sel:
                df = df[df["month_label"].isin(sel)]

        for dim in DIMENSIONS:
            opts = segment_order(dataset, dim)
            sel = st.multiselect(spec.dim_labels[dim], opts, key=f"f_{dataset}_{dim}",
                                 placeholder="All")
            if sel:
                df = df[df[dim].isin(sel)]

        min_sessions = st.slider(
            "Minimum sessions per segment", 0, 2000, 200 if dataset != "uci" else 100, 50,
            key=f"min_{dataset}",
            help="Segments smaller than this are hidden from segment charts and opportunity sizing.",
        )
        st.caption(f"{num(df['sessions'].sum())} of {num(full['sessions'].sum())} sessions selected")

    return Ctx(dataset, spec, df, full, mode, min_sessions,
               filters_active=len(df) != len(full))


def ctx() -> Ctx:
    return st.session_state["_ctx"]


def dataset_banner(c: Ctx) -> None:
    if not c.spec.is_real:
        st.warning(
            "**Simulated data.** This dataset only demonstrates the GA4 pipeline. Export the "
            "real Google Merchandise Store sample (free BigQuery sandbox, see the README) to "
            "get real findings.", icon="⚠️",
        )
    with st.expander(f"About this dataset: {c.spec.name}", expanded=False):
        st.markdown(f"**Source:** {c.spec.source}")
        for cav in c.spec.caveats:
            st.markdown(f"- {cav}")


def empty_guard(c: Ctx) -> bool:
    if c.df.empty or c.df["sessions"].sum() == 0:
        st.info("No sessions match the current filters.")
        return True
    return False
