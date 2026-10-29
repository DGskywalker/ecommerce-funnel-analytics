import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import charts
import common as c
from funnel_analytics import metrics as m

ctx = c.ctx()
spec, df = ctx.spec, ctx.df

st.title("Revenue & opportunity sizing")
c.dataset_banner(ctx)
if c.empty_guard(ctx):
    st.stop()

if spec.has_revenue:
    k = m.kpis(df, spec, ctx.mode)
    cols = st.columns(4)
    cols[0].metric("Revenue", c.money(k["revenue"]))
    cols[1].metric("Transactions", c.num(k["transactions"]))
    cols[2].metric("AOV", c.money(k["aov"], 2))
    cols[3].metric("Revenue / session", c.money(k["revenue_per_session"], 2))

    t = m.trend(df, spec, "day")
    c.show(charts.line(t, "period", [("revenue", "Revenue", c.SERIES[0])], "Daily revenue",
                       yfmt="$,.0f"), height=300)

    a, b = st.columns(2)
    for col, dim in ((a, "channel"), (b, "device")):
        seg = m.segment_table(df, dim, spec, ctx.mode, ctx.min_sessions)
        with col:
            c.show(charts.bars(seg, dim, "revenue_per_session", f"Revenue per session by {dim}",
                               fmt="$,.2f"))
            c.show(charts.bars(seg, dim, "aov", f"AOV by {dim}", fmt="$,.2f", color=c.SERIES[2]))

    st.markdown("##### Revenue concentration by country")
    p = m.pareto(df, "region").head(20)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=p["region"], y=p["revenue"], marker=dict(color=c.SERIES[0], cornerradius=4),
                         hovertemplate="<b>%{x}</b><br>Revenue $%{y:,.0f}<extra></extra>", name="Revenue"))
    fig.update_layout(title="Top 20 countries by revenue", yaxis=dict(tickformat="$,.0f"),
                      xaxis=dict(type="category"), showlegend=False)
    c.show(fig, height=320)
    top_n = int((m.pareto(df, "region")["cum_share"] <= 0.8).sum()) + 1
    st.caption(f"{top_n} countries bring in 80% of revenue for the current selection.")
else:
    st.info("This dataset has no order values, so the sizing below counts **purchases**, not revenue.")

st.divider()
st.subheader("What-if: lift one funnel step")
steps = spec.observed_steps[1:]
w1, w2 = st.columns([1, 2])
with w1:
    step = st.selectbox("Step to improve", steps, index=len(steps) - 1, format_func=spec.label)
    uplift = st.slider("Relative uplift of that step's conversion", 0, 50, 10, 1, format="%d%%") / 100
    res = m.what_if(df, spec, step, uplift, ctx.mode)
    st.metric("Extra purchases", f"+{c.num(res['extra_purchases'])}",
              f"{res['extra_purchases'] / res['base_purchases']:+.1%}" if res["base_purchases"] else None)
    if spec.has_revenue:
        st.metric("Extra revenue (at current AOV)", c.money(res["extra_revenue"]))
with w2:
    comp = pd.DataFrame({"step": [spec.label(s) for s in res["base_counts"].index],
                         "Current": res["base_counts"].values, "Scenario": res["new_counts"].values})
    fig = go.Figure()
    fig.add_trace(go.Bar(x=comp["step"], y=comp["Current"], name="Current",
                         marker=dict(color="#a9c9f1", cornerradius=4)))
    fig.add_trace(go.Bar(x=comp["step"], y=comp["Scenario"], name="Scenario",
                         marker=dict(color=c.SERIES[0], cornerradius=4)))
    fig.update_layout(title="Sessions reaching each step", barmode="group", yaxis=dict(type="log", title="Sessions (log)"),
                      bargroupgap=0.08)
    c.show(fig, height=340)

st.divider()
st.subheader("Ranked opportunities")
bench = st.radio("Benchmark", ["overall", "p75"], horizontal=True,
                 format_func={"overall": "All selected sessions", "p75": "Top-quartile segment"}.get)
opps = m.opportunities(df, spec, mode=ctx.mode, min_sessions=ctx.min_sessions, benchmark=bench)
if opps.empty:
    st.info("No opportunities at this threshold.")
else:
    show = opps.head(20).copy()
    show["dimension"] = show["dimension"].map(lambda d: spec.dim_labels[d].split(" (")[0])
    cols = {"dimension": "Dimension", "segment": "Segment", "transition": "Step", "entrants": "Entrants",
            "rate": "Rate", "benchmark": "Benchmark", "extra_purchases": "+ Purchases",
            "extra_purchases_pct": "+ % purchases"}
    if spec.has_revenue:
        cols |= {"extra_revenue": "+ Revenue"}
    st.dataframe(
        show[list(cols)].rename(columns=cols).style.format(
            {"Entrants": "{:,.0f}", "Rate": "{:.1%}", "Benchmark": "{:.1%}", "+ Purchases": "{:,.0f}",
             "+ % purchases": "{:.1%}", "+ Revenue": "${:,.0f}"}
        ).bar(subset=["+ Purchases"], color="#b7d3f6"),
        hide_index=True, use_container_width=True,
    )
    st.caption("Segments overlap across dimensions (a mobile session also belongs to a channel), "
               "so don't add up rows from different dimensions.")
