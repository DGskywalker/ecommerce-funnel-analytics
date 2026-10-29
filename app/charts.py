"""Reusable Plotly figures. Every chart gets hover text; colours come from common's palette."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from common import (DIVERGING, GRID, INK, INK_2, MUTED, ORDINAL_BLUE, SEQUENTIAL_BLUE, SERIES,
                    pct)


def funnel(ft: pd.DataFrame, title: str = "Conversion funnel") -> go.Figure:
    colors = ORDINAL_BLUE[-len(ft):] if len(ft) <= len(ORDINAL_BLUE) else ORDINAL_BLUE
    custom = np.column_stack([
        ft["pct_of_sessions"].map(lambda v: pct(v, 2)),
        ft["step_conversion"].map(lambda v: pct(v, 1)),
        ft["drop_off"].map(lambda v: "–" if pd.isna(v) else f"{v:,.0f}"),
    ])
    fig = go.Figure(go.Funnel(
        y=ft["label"], x=ft["sessions"], textinfo="value+percent initial",
        texttemplate="%{value:,.0f}  ·  %{percentInitial:.1%}",
        marker=dict(color=colors, line=dict(color="white", width=2)),
        connector=dict(fillcolor="#eef3fb", line=dict(width=0)),
        customdata=custom,
        hovertemplate="<b>%{y}</b><br>Sessions %{x:,.0f}<br>Of all sessions %{customdata[0]}"
                      "<br>From previous step %{customdata[1]}<br>Dropped here %{customdata[2]}<extra></extra>",
    ))
    fig.update_layout(title=title, yaxis=dict(gridcolor="rgba(0,0,0,0)"))
    return fig


def dropoff_bars(ft: pd.DataFrame) -> go.Figure:
    d = ft.iloc[1:].copy()
    short = [lbl.split(" (")[0] for lbl in ft["label"]]
    labels = [f"before {b}" for b in short[1:]]
    full = [f"{a} → {b}" for a, b in zip(ft["label"].iloc[:-1], ft["label"].iloc[1:])]
    worst = d["drop_off"].idxmax()
    fig = go.Figure(go.Bar(
        x=d["drop_off"], y=labels, orientation="h",
        marker=dict(color=["#e34948" if i == worst else "#c7c6c0" for i in d.index],
                    cornerradius=4),
        text=[f"{v:,.0f} · {pct(r)}" for v, r in zip(d["drop_off"], d["drop_off_rate"])],
        textposition="auto", insidetextanchor="end", textfont=dict(color=INK),
        customdata=full,
        hovertemplate="<b>%{customdata}</b><br>Sessions lost %{x:,.0f}<extra></extra>",
    ))
    fig.update_layout(title="Where sessions drop out (biggest leak in red)",
                      yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)", type="category"),
                      xaxis=dict(title="Sessions lost", tickformat=",.0f"), showlegend=False)
    return fig


def sankey(ft: pd.DataFrame) -> go.Figure:
    labels = list(ft["label"]) + ["Exited"]
    exit_idx = len(labels) - 1
    src, tgt, val, col = [], [], [], []
    for i in range(len(ft) - 1):
        src += [i, i]
        tgt += [i + 1, exit_idx]
        val += [ft["sessions"].iloc[i + 1], ft["sessions"].iloc[i] - ft["sessions"].iloc[i + 1]]
        col += ["rgba(42,120,214,0.35)", "rgba(227,73,72,0.25)"]
    node_colors = ORDINAL_BLUE[-len(ft):] + ["#e34948"]
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(label=labels, color=node_colors, pad=18, thickness=16, line=dict(width=0),
                  hovertemplate="%{label}: %{value:,.0f} sessions<extra></extra>"),
        link=dict(source=src, target=tgt, value=val, color=col,
                  hovertemplate="%{source.label} → %{target.label}: %{value:,.0f}<extra></extra>"),
    ))
    fig.update_layout(title="Session flow: progress vs exit at each step", font=dict(size=12, color=INK))
    return fig


def rate_bars(seg: pd.DataFrame, dim: str, rate_col: str, lo: str, hi: str,
              overall: float, title: str, sig_col: str | None = None) -> go.Figure:
    seg = seg.sort_values(rate_col)
    if sig_col:
        color = [SERIES[0] if s else "#a9c9f1" for s in seg[sig_col]]
    else:
        color = SERIES[0]
    fig = go.Figure(go.Bar(
        x=seg[rate_col], y=seg[dim], orientation="h",
        marker=dict(color=color, cornerradius=4),
        error_x=dict(type="data", symmetric=False, array=seg[hi] - seg[rate_col],
                     arrayminus=seg[rate_col] - seg[lo], color=MUTED, thickness=1.2, width=3),
        customdata=np.column_stack([seg["sessions"], seg[lo], seg[hi]]),
        hovertemplate="<b>%{y}</b><br>Rate %{x:.2%}<br>95% CI %{customdata[1]:.2%} – %{customdata[2]:.2%}"
                      "<br>Sessions %{customdata[0]:,.0f}<extra></extra>",
    ))
    fig.add_vline(x=overall, line=dict(color=INK_2, width=1.5, dash="dot"),
                  annotation_text=f"All selected {pct(overall, 2)}", annotation_position="top",
                  annotation_font=dict(color=INK_2, size=11))
    fig.update_layout(title=title, xaxis=dict(tickformat=".1%", title=None),
                      yaxis=dict(gridcolor="rgba(0,0,0,0)", type="category"), showlegend=False,
                      height=max(280, 34 * len(seg) + 110))
    return fig


def step_small_multiples(long: pd.DataFrame, dim: str, overall: dict, cmap: dict) -> go.Figure:
    from plotly.subplots import make_subplots
    trans = long["transition"].unique().tolist()
    fig = make_subplots(rows=1, cols=len(trans), shared_yaxes=True, subplot_titles=trans,
                        horizontal_spacing=0.04)
    order = (long.groupby(dim)["entrants"].max().sort_values().index.tolist())
    for j, t in enumerate(trans, 1):
        d = long[long["transition"] == t].set_index(dim).reindex(order).reset_index()
        fig.add_trace(go.Bar(
            x=d["rate"], y=d[dim], orientation="h",
            marker=dict(color=[cmap.get(s, SERIES[0]) for s in d[dim]], cornerradius=3),
            error_x=dict(type="data", symmetric=False, array=d["ci_high"] - d["rate"],
                         arrayminus=d["rate"] - d["ci_low"], color=MUTED, thickness=1, width=2),
            customdata=np.column_stack([d["entrants"], d["converted"]]),
            hovertemplate="<b>%{y}</b><br>" + t + "<br>Rate %{x:.1%}"
                          "<br>%{customdata[1]:,.0f} of %{customdata[0]:,.0f}<extra></extra>",
            showlegend=False,
        ), row=1, col=j)
        step = d["step"].dropna().iloc[0] if d["step"].notna().any() else None
        if step in overall:
            fig.add_vline(x=overall[step], line=dict(color=INK_2, width=1, dash="dot"), row=1, col=j)
        fig.update_xaxes(tickformat=".0%", row=1, col=j)
    fig.update_yaxes(type="category", gridcolor="rgba(0,0,0,0)")
    fig.update_annotations(font=dict(size=12, color=INK))
    fig.update_layout(title="Step conversion by segment (dotted line = all selected sessions)",
                      height=max(300, 30 * len(order) + 130))
    return fig


def heatmap(ct: pd.DataFrame, row: str, col: str, value: str = "conversion_rate",
            title: str = "", fmt: str = ".2%") -> go.Figure:
    piv = ct.pivot(index=row, columns=col, values=value)
    n = ct.pivot(index=row, columns=col, values="sessions").reindex_like(piv)
    piv = piv.loc[n.sum(axis=1).sort_values(ascending=True).index]
    n = n.loc[piv.index]
    text = [[("" if pd.isna(v) else format(v, fmt)) for v in r] for r in piv.values]
    fig = go.Figure(go.Heatmap(
        z=piv.values, x=piv.columns, y=piv.index, colorscale=SEQUENTIAL_BLUE,
        text=text, texttemplate="%{text}", textfont=dict(size=11),
        customdata=n.values, xgap=2, ygap=2,
        hovertemplate="<b>%{y} · %{x}</b><br>Value %{z:" + fmt + "}<br>Sessions %{customdata:,.0f}<extra></extra>",
        colorbar=dict(tickformat=fmt, thickness=10, outlinewidth=0),
    ))
    fig.update_layout(title=title, xaxis=dict(side="top", gridcolor="rgba(0,0,0,0)", type="category"),
                      yaxis=dict(gridcolor="rgba(0,0,0,0)", type="category"),
                      height=max(300, 30 * len(piv) + 130))
    return fig


def lift_heatmap(ct: pd.DataFrame, row: str, col: str, overall: float, title: str) -> go.Figure:
    ct = ct.copy()
    ct["lift"] = ct["conversion_rate"] / overall - 1
    piv = ct.pivot(index=row, columns=col, values="lift")
    lim = float(np.nanmax(np.abs(piv.values))) if np.isfinite(piv.values).any() else 1
    fig = go.Figure(go.Heatmap(
        z=piv.values, x=piv.columns, y=piv.index, colorscale=DIVERGING, zmid=0, zmin=-lim, zmax=lim,
        text=[[("" if pd.isna(v) else f"{v:+.0%}") for v in r] for r in piv.values],
        texttemplate="%{text}", xgap=2, ygap=2,
        hovertemplate="<b>%{y} · %{x}</b><br>Lift vs overall %{z:+.1%}<extra></extra>",
        colorbar=dict(tickformat="+.0%", thickness=10, outlinewidth=0),
    ))
    fig.update_layout(title=title, xaxis=dict(side="top", type="category"), yaxis=dict(type="category"),
                      height=max(300, 30 * len(piv) + 130))
    return fig


def line(df: pd.DataFrame, x: str, ys: list[tuple[str, str, str]], title: str,
         yfmt: str = ",.0f", band: tuple[str, str] | None = None, markers_col: str | None = None) -> go.Figure:
    """ys: (column, name, colour). One y-axis only."""
    fig = go.Figure()
    if band:
        fig.add_trace(go.Scatter(x=pd.concat([df[x], df[x][::-1]]),
                                 y=pd.concat([df[band[1]], df[band[0]][::-1]]),
                                 fill="toself", fillcolor="rgba(42,120,214,0.10)",
                                 line=dict(width=0), hoverinfo="skip", name="95% CI",
                                 showlegend=True))
    for col, name, color in ys:
        fig.add_trace(go.Scatter(x=df[x], y=df[col], name=name, mode="lines",
                                 line=dict(color=color, width=2),
                                 hovertemplate=f"{name} %{{y:{yfmt}}}<extra></extra>"))
    if markers_col is not None and df[markers_col].any():
        a = df[df[markers_col]]
        fig.add_trace(go.Scatter(x=a[x], y=a[ys[0][0]], mode="markers", name="Anomaly (|z| > 2)",
                                 marker=dict(size=9, color="#d03b3b", line=dict(color="white", width=2),
                                             symbol="diamond"),
                                 hovertemplate="Anomaly %{x}<br>%{y:" + yfmt + "}<extra></extra>"))
    fig.update_layout(title=title, hovermode="x unified", yaxis=dict(tickformat=yfmt))
    return fig


def bars(df: pd.DataFrame, x: str, y: str, title: str, fmt: str = ",.0f", color: str = SERIES[0],
         horizontal: bool = True, hover_extra: str = "") -> go.Figure:
    d = df.sort_values(y if horizontal else x, ascending=True)
    kw = dict(x=d[y], y=d[x], orientation="h") if horizontal else dict(x=d[x], y=d[y])
    fig = go.Figure(go.Bar(**kw, marker=dict(color=color, cornerradius=4),
                           hovertemplate="<b>%{" + ("y" if horizontal else "x") + "}</b><br>%{"
                           + ("x" if horizontal else "y") + ":" + fmt + "}" + hover_extra + "<extra></extra>"))
    ax = dict(tickformat=fmt)
    fig.update_layout(title=title, showlegend=False,
                      **({"xaxis": ax, "yaxis": dict(type="category", gridcolor="rgba(0,0,0,0)")}
                         if horizontal else {"yaxis": ax, "xaxis": dict(type="category")}))
    if horizontal:
        fig.update_layout(height=max(260, 30 * len(d) + 110))
    return fig


def bubble(seg: pd.DataFrame, dim: str, size_col: str, title: str, overall: float) -> go.Figure:
    s = seg[size_col].fillna(0)
    sizes = 12 + 40 * np.sqrt(s / s.max()) if s.max() > 0 else np.full(len(s), 16)
    fig = go.Figure(go.Scatter(
        x=seg["share"], y=seg["conversion_rate"], mode="markers+text", text=seg[dim],
        textposition="top center", textfont=dict(size=11, color=INK_2),
        marker=dict(size=sizes, color="rgba(42,120,214,0.55)", line=dict(color="white", width=2)),
        customdata=np.column_stack([seg["sessions"], s]),
        hovertemplate="<b>%{text}</b><br>Traffic share %{x:.1%}<br>Conversion %{y:.2%}"
                      "<br>Sessions %{customdata[0]:,.0f}<br>" + size_col.replace("_", " ").title()
                      + " %{customdata[1]:,.0f}<extra></extra>",
    ))
    fig.add_hline(y=overall, line=dict(color=INK_2, width=1, dash="dot"))
    fig.update_layout(title=title, xaxis=dict(title="Share of sessions", tickformat=".0%"),
                      yaxis=dict(title="Conversion rate", tickformat=".1%"), showlegend=False)
    return fig


__all__ = ["funnel", "dropoff_bars", "sankey", "rate_bars", "step_small_multiples", "heatmap",
           "lift_heatmap", "line", "bars", "bubble", "GRID", "INK"]
