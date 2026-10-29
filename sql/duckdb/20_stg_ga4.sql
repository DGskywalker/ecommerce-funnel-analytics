-- Staging: GA4-export layout (real export or simulated demo) → unified session schema.
-- Templated by warehouse.py: {dataset} is the dataset key, {source} the raw table.
CREATE OR REPLACE TABLE stg_{dataset} AS
SELECT
  '{dataset}'                                                    AS dataset,
  CAST(session_id AS VARCHAR)                                    AS session_id,
  CAST(session_date AS DATE)                                     AS session_date,
  year(CAST(session_date AS DATE)) * 100 + month(CAST(session_date AS DATE)) AS month_sort,
  strftime(CAST(session_date AS DATE), '%Y-%m')                  AS month_label,
  channel_group(
    COALESCE(NULLIF(session_source, ''), NULLIF(user_source, '')),
    COALESCE(NULLIF(session_medium, ''), NULLIF(user_medium, ''))
  )                                                              AS channel,
  CASE lower(device_category)
    WHEN 'desktop' THEN 'Desktop'
    WHEN 'mobile'  THEN 'Mobile'
    WHEN 'tablet'  THEN 'Tablet'
    ELSE 'Other'
  END                                                            AS device,
  COALESCE(NULLIF(country, ''), '(not set)')                     AS region,
  CASE
    WHEN ga_session_number = 1 THEN 'New'
    WHEN ga_session_number > 1 THEN 'Returning'
    ELSE 'Other'
  END                                                            AS visitor_type,
  dayofweek(CAST(session_date AS DATE)) IN (0, 6)                AS is_weekend,
  CAST(COALESCE(pageviews, 0) AS INTEGER)                        AS pageviews,
  CAST(COALESCE(engagement_sec, 0) AS DOUBLE)                    AS engagement_sec,
  CAST(has_view_item AS BOOLEAN)                                 AS s_view,
  CAST(has_add_to_cart AS BOOLEAN)                               AS s_cart,
  CAST(has_begin_checkout AS BOOLEAN)                            AS s_checkout,
  CAST(has_purchase AS BOOLEAN)                                  AS s_purchase,
  CAST(COALESCE(transactions, 0) AS INTEGER)                     AS transactions,
  CAST(COALESCE(purchase_revenue_usd, 0) AS DOUBLE)              AS revenue
FROM {source};
