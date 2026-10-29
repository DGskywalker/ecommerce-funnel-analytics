import streamlit as st

import charts
import common as c
from funnel_analytics import metrics as m

ctx = c.ctx()
spec, df = ctx.spec, ctx.df

st.title("Executive overview")
st.caption(f"{spec.name} · {ctx.mode} funnel")
c.dataset_banner(ctx)
if c.empty_guard(ctx):
    st.stop()

k = m.kpis(df, spec, ctx.mode)
cols = st.columns(6 if spec.has_revenue else 4)
cols[0].metric("Sessions", c.num(k["sessions"]))
cols[1].metric("Conversion rate", c.pct(k["conversion_rate"], 2),
               help="Sessions with at least one purchase ÷ all sessions (open count).")
cols[2].metric("Purchasing sessions", c.num(k["purchasing_sessions"]))
if spec.has_revenue:
    cols[3].metric("Revenue", c.money(k["revenue"]))
    cols[4].metric("AOV", c.money(k["aov"], 2), help="Revenue ÷ transactions.")
    cols[5].metric("Revenue / session", c.money(k["revenue_per_session"], 2))
else:
    cols[3].metric("Checkout-proxy abandonment", c.pct(k.get("checkout_abandonment")),
                   help="Share of purchase-path sessions (PageValues > 0) that did not buy.")

ft = m.funnel_table(df, spec, ctx.mode)
left, right = st.columns([3, 2])
with left:
    c.show(charts.funnel(ft), height=380)
with right:
    c.show(charts.dropoff_bars(ft), height=380)

st.subheader("Where the next purchases will come from")
opps = m.opportunities(df, spec, mode=ctx.mode, min_sessions=ctx.min_sessions)
if opps.empty:
    st.info("No segment falls below the site benchmark with the current filters.")
else:
    from funnel_analytics.writeup import pick_recommendations
    top = pick_recommendations(opps, 3)
    for col, (_, r) in zip(st.columns(3), top.iterrows()):
        with col.container(border=True):
            st.markdown(f"**{spec.dim_labels[r['dimension']].split(' (')[0]}: {r['segment']}**")
            st.caption(r["transition"])
            st.markdown(f"Step rate **{c.pct(r['rate'])}** vs **{c.pct(r['benchmark'])}** for all selected sessions")
            msg = f"+{c.num(r['extra_purchases'])} purchases ({c.pct(r['extra_purchases_pct'])})"
            if spec.has_revenue:
                msg += f" · ≈ {c.money(r['extra_revenue'])}"
            st.markdown(f":blue[**{msg}**] if it closes the gap")

st.subheader("Conversion at a glance")
g1, g2 = st.columns(2)
for col, dim in ((g1, "device"), (g2, "channel")):
    seg = m.segment_table(df, dim, spec, ctx.mode, ctx.min_sessions)
    if spec.key == "uci" and dim == "channel":
        seg = seg.head(10)
    with col:
        c.show(charts.rate_bars(seg, dim, "conversion_rate", "ci_low", "ci_high",
                                k["conversion_rate"], f"Conversion rate by {spec.dim_labels[dim].lower()}",
                                sig_col="significant"))
st.caption("Dark bars: the difference from all other sessions is statistically significant "
           "(two-proportion z-test, Benjamini–Hochberg FDR < 5%). Whiskers: 95% Wilson interval.")
