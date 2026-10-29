import streamlit as st

import charts
import common as c
from funnel_analytics import metrics as m

ctx = c.ctx()
spec, df = ctx.spec, ctx.df

st.title("Channels & devices")
c.dataset_banner(ctx)
if c.empty_guard(ctx):
    st.stop()

overall = m.kpis(df, spec, ctx.mode)["conversion_rate"]
dim = st.segmented_control("Dimension", list(spec.dim_labels), default="channel",
                           format_func=lambda d: spec.dim_labels[d].split(" (")[0], key="seg_dim") or "channel"
seg = m.segment_table(df, dim, spec, ctx.mode, ctx.min_sessions)
chi = m.chi_square_independence(df, dim, max(ctx.min_sessions, 30))

s1, s2, s3 = st.columns(3)
s1.metric("Segments shown", f"{len(seg)}")
s2.metric("χ² test p-value", "< 0.001" if chi["p_value"] < 0.001 else f"{chi['p_value']:.3f}",
          help="Null hypothesis: conversion does not depend on this dimension.")
s3.metric("Effect size (Cramér's V)", f"{chi['cramers_v']:.3f}",
          help="0.1 is small, 0.3 medium, 0.5 large.")

a, b = st.columns(2)
with a:
    c.show(charts.rate_bars(seg.head(15), dim, "conversion_rate", "ci_low", "ci_high", overall,
                            "Conversion rate (95% CI)", sig_col="significant"))
with b:
    size_col = "revenue" if spec.has_revenue else "purchases"
    c.show(charts.bubble(seg.head(15), dim, size_col,
                         f"Traffic share vs conversion (bubble = {size_col})", overall), height=420)

st.markdown("##### Segment scorecard")
cols = {dim: spec.dim_labels[dim].split(" (")[0], "sessions": "Sessions", "share": "Share",
        "purchases": "Purchases", "conversion_rate": "CR", "lift_vs_rest": "Lift vs rest",
        "p_adj": "p (BH-adj.)"}
if spec.has_revenue:
    cols |= {"revenue": "Revenue", "revenue_share": "Revenue share", "aov": "AOV",
             "revenue_per_session": "Rev / session"}
cols |= {f"cr_{s}": f"→ {spec.label(s)}" for s in spec.observed_steps[1:]}
view = seg[list(cols)].rename(columns=cols)
fmt = {"Sessions": "{:,.0f}", "Purchases": "{:,.0f}", "Share": "{:.1%}", "CR": "{:.2%}",
       "Lift vs rest": "{:+.0%}", "p (BH-adj.)": "{:.3g}", "Revenue": "${:,.0f}",
       "Revenue share": "{:.1%}", "AOV": "${:,.2f}", "Rev / session": "${:,.2f}"}
fmt |= {v: "{:.1%}" for k, v in cols.items() if k.startswith("cr_")}
st.dataframe(
    view.style.format(fmt, na_rep="–").background_gradient(subset=["Lift vs rest"], cmap="RdBu",
                                                           vmin=-1, vmax=1),
    hide_index=True, use_container_width=True,
)
st.download_button("Download scorecard (CSV)", seg.to_csv(index=False).encode(),
                   f"segments_{ctx.dataset}_{dim}.csv", "text/csv")

st.divider()
st.subheader("Channel × device")
ct = m.cross_tab(c.fold_other(c.fold_other(df, ctx.dataset, "channel"), ctx.dataset, "device"),
                 "channel", "device", max(ctx.min_sessions // 4, 30))
x, y = st.columns(2)
with x:
    c.show(charts.heatmap(ct, "channel", "device", title="Conversion rate"))
with y:
    c.show(charts.lift_heatmap(ct, "channel", "device", overall,
                               "Lift vs all selected sessions (red = below, blue = above)"))
st.caption("Cells with fewer sessions than a quarter of the minimum (and never fewer than 30) are left blank.")
