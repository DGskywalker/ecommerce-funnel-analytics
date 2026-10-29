# Where the funnel leaks, and three fixes

**Data:** UCI Online Shoppers Purchasing Intention (real, 12,330 sessions over one year, CC BY 4.0).
**Funnel:** Session → Product page view → Purchase-path page (PageValues > 0) → Purchase.
**Method:** DuckDB marts, Wilson 95% intervals, two-proportion z-tests with Benjamini–Hochberg correction, gap-to-benchmark sizing, gradient-boosted propensity model. All numbers can be reproduced with `make all`.

## Headline

- **15.5% of sessions convert** (1,908 of 12,330). Almost every session views a product (99.7%), so landing on the catalogue is not the problem.
- **The biggest leak is browse → intent.** Only **22.2%** of product-viewing sessions reach a purchase-path page, so 9,562 sessions (78%) leave without one. Sessions that do reach one convert at **56.3%**.
- **Conversion is very seasonal.** November converts at **25.4%**; May has the most traffic (27% of sessions) but converts at only **10.9%**. Sessions close to a special day convert at **6.2%**, against 16.5% for all other sessions.
- **Segment differences are real, not noise.** Traffic type, OS and visitor type all have χ² p < 0.001. Traffic type has the largest effect (Cramér's V 0.17).

## Three recommendations

**1. Re-engage returning visitors who stall at the decision point.**
Returning visitors reach purchase-path pages as often as new visitors (22.2% vs 22.6%), but only **51%** of them buy from there, against **86%** of new visitors. They make up 86% of traffic, so this is the largest single gap. Closing it to the site average (56%) is worth **+119 purchases (+7.8%)**.
*Action:* a cart and wishlist that persist across sessions, price-drop and back-in-stock emails, retargeting aimed at purchase-path sessions that didn't buy, and comparison or reassurance content (returns, delivery dates) on decision pages. *Track:* purchase-path → purchase rate for returning visitors, as an A/B test.

**2. Fix the traffic sources that browse but never show intent.**
Traffic type 03 (17% of sessions) moves only **13.7%** of product viewers onto the purchase path, against 22.2% overall, and converts at 8.8% in total. Type 13 converts at **5.8%**. Lifting type 03 to the site rate is worth **+94 purchases (+6.1%)**.
*Action:* check the landing pages and ad promises for these sources, send them to curated product lists instead of generic pages, and add clear next-step calls to action and related products. If quality doesn't improve, move budget toward type 02 (21.7% CR) and type 08 (27.7% CR). *Track:* product view → purchase-path rate by source.

**3. Sell earlier in the run-up to special days, and make May work harder.**
Sessions close to a special day convert at less than half the normal rate (6.2% vs 16.5%): people browse, then buy elsewhere or too late. May has the most traffic of any month and the second-lowest conversion. If May converted at the annual average, that alone would add about **+155 purchases**.
*Action:* start gift campaigns 2–3 weeks before the event, show a guaranteed-delivery date on product pages, and add last-order countdowns. Move May spend from awareness toward retargeting returning, high-intent sessions (see recommendation 1). *Track:* conversion rate within 14 days of each special day, year on year.

## Targeting support

A gradient-boosting model that leaves out the leaky `PageValues` feature still reaches **ROC AUC 0.77**. Its top score decile converts at **2.8×** the base rate and captures 28% of all purchases. It can be used as a seed audience for the retargeting in recommendations 1 and 3. With `PageValues` included the AUC rises to 0.93, but that version mostly restates the outcome.

## Caveats

The UCI funnel is a proxy: there are no cart or checkout events and no order values, and traffic type, OS and region are anonymised codes. Impact figures come from a mechanical gap-to-benchmark calculation, not a forecast, so treat each one as an upper bound to test, not as a promise. The same pipeline produces the full five-step funnel with revenue from the **GA4 Merchandise Store** export (see the README). The dashboard's *Write-up* page drafts this report again from whichever dataset is loaded.
