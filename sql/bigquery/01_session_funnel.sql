-- =============================================================================
-- GA4 obfuscated sample → one row per session, ready for the DuckDB pipeline.
--
-- Runs in the FREE BigQuery sandbox (no billing account, no API key):
--   1. Open https://console.cloud.google.com/bigquery and sign in with a Google account.
--   2. Paste this query and run it. It scans a small fraction of the 1 TB/month free query tier.
--   3. Save results → "CSV (Google Drive)" (the local CSV download is capped at 10 MB;
--      the full session-level output is larger than that). Or save to a sandbox table and export it.
--   4. Put the file(s) in data/raw/ga4/ and run `make build`.
--
-- Output columns match funnel_analytics.ingest.simulate exactly, so the demo
-- and the real export go through the same staging model (sql/duckdb/20_stg_ga4.sql).
-- =============================================================================

DECLARE start_suffix STRING DEFAULT '20201101';
DECLARE end_suffix   STRING DEFAULT '20210131';

WITH events AS (
  SELECT
    user_pseudo_id,
    (SELECT value.int_value    FROM UNNEST(event_params) WHERE key = 'ga_session_id')        AS ga_session_id,
    (SELECT value.int_value    FROM UNNEST(event_params) WHERE key = 'ga_session_number')    AS ga_session_number,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'source')               AS ep_source,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'medium')               AS ep_medium,
    (SELECT value.int_value    FROM UNNEST(event_params) WHERE key = 'engagement_time_msec') AS engagement_msec,
    event_name,
    event_timestamp,
    PARSE_DATE('%Y%m%d', event_date)     AS event_date,
    device.category                      AS device_category,
    geo.country                          AS country,
    traffic_source.source                AS user_source,
    traffic_source.medium                AS user_medium,
    ecommerce.transaction_id             AS transaction_id,
    ecommerce.purchase_revenue_in_usd    AS purchase_revenue_usd
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE _TABLE_SUFFIX BETWEEN start_suffix AND end_suffix
),

sessionised AS (
  SELECT *, CONCAT(user_pseudo_id, '-', CAST(ga_session_id AS STRING)) AS session_id
  FROM events
  WHERE ga_session_id IS NOT NULL
),

-- The sample has duplicate purchase events per transaction: keep one value each.
transactions AS (
  SELECT session_id, transaction_id, MAX(purchase_revenue_usd) AS revenue_usd
  FROM sessionised
  WHERE event_name = 'purchase'
    AND transaction_id IS NOT NULL
    AND transaction_id NOT IN ('(not set)', '')
  GROUP BY session_id, transaction_id
),

txn_by_session AS (
  SELECT session_id, COUNT(*) AS transactions, SUM(IFNULL(revenue_usd, 0)) AS purchase_revenue_usd
  FROM transactions
  GROUP BY session_id
)

SELECT
  s.session_id,
  MIN(s.event_date)                                                                   AS session_date,
  MAX(s.ga_session_number)                                                            AS ga_session_number,
  ARRAY_AGG(s.ep_source IGNORE NULLS ORDER BY s.event_timestamp LIMIT 1)[SAFE_OFFSET(0)] AS session_source,
  ARRAY_AGG(s.ep_medium IGNORE NULLS ORDER BY s.event_timestamp LIMIT 1)[SAFE_OFFSET(0)] AS session_medium,
  ANY_VALUE(s.user_source)                                                            AS user_source,
  ANY_VALUE(s.user_medium)                                                            AS user_medium,
  ANY_VALUE(s.device_category)                                                        AS device_category,
  ANY_VALUE(s.country)                                                                AS country,
  COUNTIF(s.event_name = 'page_view')                                                 AS pageviews,
  ROUND(SUM(IFNULL(s.engagement_msec, 0)) / 1000, 1)                                  AS engagement_sec,
  LOGICAL_OR(s.event_name = 'view_item')                                              AS has_view_item,
  LOGICAL_OR(s.event_name = 'add_to_cart')                                            AS has_add_to_cart,
  LOGICAL_OR(s.event_name = 'begin_checkout')                                         AS has_begin_checkout,
  LOGICAL_OR(s.event_name = 'purchase')                                               AS has_purchase,
  IFNULL(ANY_VALUE(t.transactions), 0)                                                AS transactions,
  IFNULL(ANY_VALUE(t.purchase_revenue_usd), 0)                                        AS purchase_revenue_usd
FROM sessionised AS s
LEFT JOIN txn_by_session AS t USING (session_id)
GROUP BY s.session_id;
