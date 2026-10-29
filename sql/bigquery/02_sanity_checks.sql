-- Quick checks to run in the BigQuery console before exporting.
-- Each one scans only a few hundred MB in the free sandbox.

-- 1) Is the dataset still there, and which dates does it cover?
SELECT
  MIN(event_date) AS first_day,
  MAX(event_date) AS last_day,
  COUNT(*)        AS events,
  COUNT(DISTINCT user_pseudo_id) AS users
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`;

-- 2) Event volume for the five funnel events
SELECT event_name, COUNT(*) AS events
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE event_name IN ('session_start', 'view_item', 'add_to_cart', 'begin_checkout', 'purchase')
GROUP BY event_name
ORDER BY events DESC;

-- 3) Which source/medium values exist (drives the channel-grouping macro)
SELECT
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'medium') AS medium,
  COUNT(*) AS events
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE event_name = 'session_start'
GROUP BY medium
ORDER BY events DESC;
