-- Marts: the aggregated grain the dashboard reads.
-- "open" counts every session that fired a step; "closed" counts only sessions
-- that also passed every earlier step the dataset can observe.

CREATE OR REPLACE TABLE mart_funnel AS
SELECT
  dataset, session_date, month_sort, month_label,
  channel, device, region, visitor_type, is_weekend,
  COUNT(*)                         AS sessions,
  SUM(CAST(s_view     AS INTEGER)) AS open_view,
  SUM(CAST(s_cart     AS INTEGER)) AS open_cart,
  SUM(CAST(s_checkout AS INTEGER)) AS open_checkout,
  SUM(CAST(s_purchase AS INTEGER)) AS open_purchase,
  SUM(CAST(c_view     AS INTEGER)) AS closed_view,
  SUM(CAST(c_cart     AS INTEGER)) AS closed_cart,
  SUM(CAST(c_checkout AS INTEGER)) AS closed_checkout,
  SUM(CAST(c_purchase AS INTEGER)) AS closed_purchase,
  SUM(transactions)                AS transactions,
  SUM(revenue)                     AS revenue,
  SUM(pageviews)                   AS pageviews,
  SUM(engagement_sec)              AS engagement_sec
FROM fct_sessions
GROUP BY ALL;

CREATE OR REPLACE TABLE mart_dataset_summary AS
SELECT
  dataset,
  COUNT(*)                                         AS sessions,
  SUM(CAST(s_purchase AS INTEGER))                 AS purchasing_sessions,
  SUM(transactions)                                AS transactions,
  SUM(revenue)                                     AS revenue,
  MIN(session_date)                                AS first_date,
  MAX(session_date)                                AS last_date,
  COUNT(DISTINCT channel)                          AS channels,
  COUNT(DISTINCT device)                           AS devices,
  COUNT(DISTINCT region)                           AS regions,
  current_timestamp                                AS built_at
FROM fct_sessions
GROUP BY dataset;
