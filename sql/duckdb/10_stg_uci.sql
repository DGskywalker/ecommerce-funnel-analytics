-- Staging: UCI Online Shoppers → unified session schema.
-- Proxy funnel: Session → Product page view → Purchase-path page (PageValues > 0) → Purchase.
CREATE OR REPLACE TABLE stg_uci AS
WITH src AS (
  SELECT
    *,
    CASE Month
      WHEN 'Jan' THEN 1 WHEN 'Feb' THEN 2 WHEN 'Mar' THEN 3 WHEN 'Apr' THEN 4
      WHEN 'May' THEN 5 WHEN 'June' THEN 6 WHEN 'Jun' THEN 6 WHEN 'Jul' THEN 7
      WHEN 'Aug' THEN 8 WHEN 'Sep' THEN 9 WHEN 'Oct' THEN 10 WHEN 'Nov' THEN 11
      WHEN 'Dec' THEN 12
    END AS m
  FROM raw_uci
)
SELECT
  'uci'                                                         AS dataset,
  session_id,
  CAST(NULL AS DATE)                                            AS session_date,
  m                                                             AS month_sort,
  strftime(make_date(2000, m, 1), '%b')                         AS month_label,
  'Traffic ' || lpad(CAST(TrafficType AS VARCHAR), 2, '0')      AS channel,
  'OS ' || CAST(OperatingSystems AS VARCHAR)                    AS device,
  'Region ' || CAST(Region AS VARCHAR)                          AS region,
  CASE VisitorType
    WHEN 'Returning_Visitor' THEN 'Returning'
    WHEN 'New_Visitor'       THEN 'New'
    ELSE 'Other'
  END                                                           AS visitor_type,
  CAST(Weekend AS BOOLEAN)                                      AS is_weekend,
  CAST(Administrative + Informational + ProductRelated AS INTEGER) AS pageviews,
  CAST(Administrative_Duration + Informational_Duration + ProductRelated_Duration AS DOUBLE)
                                                                AS engagement_sec,
  ProductRelated > 0                                            AS s_view,
  CAST(NULL AS BOOLEAN)                                         AS s_cart,
  PageValues > 0                                                AS s_checkout,
  CAST(Revenue AS BOOLEAN)                                      AS s_purchase,
  CASE WHEN CAST(Revenue AS BOOLEAN) THEN 1 ELSE 0 END          AS transactions,
  CAST(NULL AS DOUBLE)                                          AS revenue
FROM src;
