"""Draft a one-page write-up from the warehouse: `python -m funnel_analytics.writeup --dataset uci`.

The findings and the sizing come straight from metrics.py. The recommendation
wording comes from a playbook keyed on the funnel step where the gap sits.
Treat the output as a first draft: an analyst should read it and edit it.
"""
from __future__ import annotations

import argparse
from datetime import date

import numpy as np
import pandas as pd

from . import metrics as m
from . import warehouse
from .config import DATASETS, DOCS_DIR

PLAYBOOK = {
    "view": (
        "Get more landing traffic to a product page",
        "Send campaign and referral traffic to category or product pages instead of the home "
        "page. Put best-sellers above the fold, and give the source a matching landing page.",
        "Product-view rate for the segment",
    ),
    "cart": (
        "Make product pages convert to cart",
        "Show price, shipping cost and delivery date on the product page. Add size and fit "
        "help, reviews and a sticky add-to-cart button. Test free-shipping thresholds.",
        "Add-to-cart rate (product view → cart)",
    ),
    "checkout": (
        "Move carts into checkout",
        "Add a persistent mini-cart, express-pay buttons on the cart page, and cart-abandonment "
        "emails at 1 h and 24 h. Remove surprise costs before checkout starts.",
        "Checkout-start rate (cart → checkout)",
    ),
    "purchase": (
        "Fix checkout completion",
        "Turn on guest checkout and wallet payments (Apple Pay / Google Pay), cut form fields, "
        "add address autocomplete, and watch for payment errors by device.",
        "Checkout completion rate (checkout → purchase)",
    ),
}
UCI_PLAYBOOK = {
    "checkout": (
        "Pull more product browsers onto the purchase path",
        "Sessions that view products but never reach a page with PageValues > 0 make up the "
        "biggest drop. Add stronger calls to action, related-product modules and clearer paths "
        "from product lists to the pages that come before a purchase.",
        "Share of product-viewing sessions that reach a purchase-path page",
    ),
    "purchase": (
        "Close the purchase-path sessions",
        "These sessions reached a page that comes before purchases but did not buy. Retarget "
        "them, test reassurance at the decision point (returns, delivery, payment options) and "
        "time-limited incentives around special days.",
        "Purchase rate among purchase-path sessions",
    ),
}


def _pct(x, d=1):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x * 100:.{d}f}%"


def _money(x):
    return "n/a" if x is None or np.isnan(x) else f"${x:,.0f}"


def pick_recommendations(opps: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """Take the biggest opportunities, spread across funnel steps first, then dimensions."""
    picked, used_steps, used_pairs = [], set(), set()
    # A new step only gets a slot ahead of a bigger repeat if it is at least
    # a quarter the size of the top opportunity.
    floor = 0.25 * opps["extra_purchases"].max() if len(opps) else 0
    for pass_ in ("new_step", "new_pair"):
        for i, r in opps.iterrows():
            if len(picked) == n:
                break
            pair = (r["dimension"], r["step"])
            if pair in used_pairs or i in picked:
                continue
            if pass_ == "new_step" and (r["step"] in used_steps or r["extra_purchases"] < floor):
                continue
            picked.append(i)
            used_steps.add(r["step"])
            used_pairs.add(pair)
    return opps.loc[sorted(picked)]


def build(con, dataset: str) -> str:
    spec = DATASETS[dataset]
    df = con.execute("SELECT * FROM mart_funnel WHERE dataset = ?", [dataset]).df()
    if df.empty:
        raise LookupError(f"No '{dataset}' sessions in the warehouse. Load that dataset first.")
    k = m.kpis(df, spec)
    f = m.funnel_table(df, spec)
    worst = f.iloc[1:].sort_values("drop_off", ascending=False).iloc[0]
    seg = {d: m.segment_table(df, d, spec, min_sessions=300) for d in ("channel", "device", "visitor_type")}
    opps = m.opportunities(df, spec, min_sessions=300)
    recs = pick_recommendations(opps)
    playbook = UCI_PLAYBOOK if dataset == "uci" else PLAYBOOK

    lines = [
        f"# Conversion funnel review: {spec.name}",
        "",
        f"*Draft generated {date.today():%d %b %Y} from `mart_funnel`. "
        f"{'**SIMULATED DATA: for demonstrating the method only.**' if not spec.is_real else 'Source: ' + spec.source}*",
        "",
        "## Headline",
        "",
    ]
    kpi_bits = [f"**{k['sessions']:,.0f} sessions**", f"**{_pct(k['conversion_rate'], 2)} conversion rate**"]
    if spec.has_revenue:
        kpi_bits += [f"**{_money(k['revenue'])} revenue**", f"{_money(k['aov'])} AOV",
                     f"${k['revenue_per_session']:.2f} revenue per session"]
    lines.append(" · ".join(kpi_bits) + ".")
    lines.append("")
    lines.append(
        f"The biggest leak is **{f.loc[f.index[f['step'] == worst['step']][0] - 1, 'label']} → "
        f"{worst['label']}**: {worst['drop_off']:,.0f} sessions ({_pct(worst['drop_off_rate'])}) "
        "drop out at this step."
    )
    lines.append("")
    lines.append("| Step | Sessions | % of sessions | Step conversion |")
    lines.append("|---|---:|---:|---:|")
    for _, r in f.iterrows():
        lines.append(f"| {r['label']} | {r['sessions']:,.0f} | {_pct(r['pct_of_sessions'])} | "
                     f"{'–' if np.isnan(r['step_conversion']) else _pct(r['step_conversion'])} |")
    lines += ["", "## What drives the gaps", ""]
    for dim, t in seg.items():
        if t.empty:
            continue
        best, worst_s = t.loc[t["conversion_rate"].idxmax()], t.loc[t["conversion_rate"].idxmin()]
        chi = m.chi_square_independence(df, dim, 300)
        sig = "significant" if chi["p_value"] < 0.05 else "not significant"
        p_txt = "< 0.001" if chi["p_value"] < 0.001 else "= {:.3f}".format(chi["p_value"])
        lines.append(
            f"- **{spec.dim_labels[dim]}:** {best[dim]} converts at {_pct(best['conversion_rate'], 2)} and "
            f"{worst_s[dim]} at {_pct(worst_s['conversion_rate'], 2)} "
            f"(χ² p {p_txt}, {sig}; "
            f"Cramér's V {chi['cramers_v']:.2f})."
        )
    lines += ["", "## Three recommendations", ""]
    for i, (_, r) in enumerate(recs.iterrows(), 1):
        title, action, kpi = playbook.get(r["step"], PLAYBOOK.get(r["step"]))
        impact = f"+{r['extra_purchases']:,.0f} purchases ({_pct(r['extra_purchases_pct'])} more)"
        if spec.has_revenue:
            impact += f", about {_money(r['extra_revenue'])} revenue over the period"
        lines += [
            f"**{i}. {title}, for {spec.dim_labels[r['dimension']].split(' (')[0].lower()} "
            f"= {r['segment']}.**",
            f"*Evidence:* {r['transition']} is {_pct(r['rate'])} for {r['segment']} vs "
            f"{_pct(r['benchmark'])} site-wide, across {r['entrants']:,.0f} sessions entering the step.",
            f"*Action:* {action}",
            f"*Impact if it closes the gap to the site average:* {impact}. *Track:* {kpi}; "
            "test it as an A/B experiment before rolling it out.",
            "",
        ]
    lines += ["## Caveats", ""] + [f"- {c}" for c in spec.caveats]
    lines.append("- Impact numbers come from a mechanical gap-to-benchmark calculation, not a "
                 "forecast. They assume the closed segment then converts downstream at its current rate.")
    return "\n".join(lines) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", default="uci", choices=list(DATASETS))
    args = p.parse_args(argv)
    con = warehouse.connect(read_only=True)
    try:
        md = build(con, args.dataset)
    except LookupError as exc:
        raise SystemExit(str(exc))
    finally:
        con.close()
    out = DOCS_DIR / f"writeup_{args.dataset}_auto.md"
    out.write_text(md)
    print(md)
    print(f"→ {out}")


if __name__ == "__main__":
    main()
