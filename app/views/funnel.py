import streamlit as st

import charts
import common as c
from funnel_analytics import metrics as m

ctx = c.ctx()
spec, df = ctx.spec, ctx.df

st.title("Funnel & drop-off")
c.dataset_banner(ctx)
if c.empty_guard(ctx):
    st.stop()

ft = m.funnel_table(df, spec, ctx.mode)
a, b = st.columns([1, 1])
with a:
    c.show(charts.funnel(ft, f"{ctx.mode.title()} funnel"), height=400)
with b:
    c.show(charts.sankey(ft), height=400)

st.markdown("##### Step table")
tbl = ft.assign(
    **{
        "Sessions": ft["sessions"].map(c.num),
        "% of sessions": ft["pct_of_sessions"].map(lambda v: c.pct(v, 2)),
        "Step conversion": ft["step_conversion"].map(c.pct),
        "95% CI": [("–" if lo != lo else f"{lo:.1%} – {hi:.1%}") for lo, hi in zip(ft["ci_low"], ft["ci_high"])],
        "Dropped": ft["drop_off"].map(c.num),
        "Drop-off rate": ft["drop_off_rate"].map(c.pct),
    }
)[["label", "Sessions", "% of sessions", "Step conversion", "95% CI", "Dropped", "Drop-off rate"]]
st.dataframe(tbl.rename(columns={"label": "Step"}), hide_index=True, use_container_width=True)

if ctx.mode == "closed":
    open_ft = m.funnel_table(df, spec, "open")
    leak = open_ft["sessions"].iloc[-1] - ft["sessions"].iloc[-1]
    if leak > 0:
        st.caption(
            f"ℹ️ {c.num(leak)} purchasing sessions skipped an earlier step (tagging gaps or "
            "deep links), so the closed funnel leaves them out. Switch to Open in the sidebar to count them."
        )

st.divider()
st.subheader("Which segments leak where?")
dim = st.segmented_control("Break down by", list(spec.dim_labels), default="device",
                           format_func=lambda d: spec.dim_labels[d].split(" (")[0], key="funnel_dim")
dim = dim or "device"
d = c.fold_other(df, ctx.dataset, dim)
long = m.step_rates_long(d, dim, spec, ctx.mode, ctx.min_sessions)
if long.empty:
    st.info("No segment meets the minimum-sessions threshold.")
else:
    overall = dict(zip(ft["step"], ft["step_conversion"]))
    c.show(charts.step_small_multiples(long, dim, overall, c.color_map(ctx.dataset, dim)))

    # Index each segment's step rate against the overall step rate so the weakest step stands out.
    long = long.assign(index=long["rate"] / long["step"].map(overall))
    piv = long.pivot(index=dim, columns="transition", values="index")
    st.markdown("##### Step-rate index (1.00 = same as all selected sessions)")
    st.dataframe(
        piv.style.format("{:.2f}").background_gradient(cmap="RdBu", vmin=0.5, vmax=1.5, axis=None),
        use_container_width=True,
    )
    st.caption("Under 1.00 means the segment converts worse than average at that step. "
               "The lowest cell in a high-traffic row is usually the best fix to start with.")
