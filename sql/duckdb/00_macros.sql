-- Default channel grouping, simplified from GA4's own rules.
-- Used for both the real export and the simulated demo so they are grouped the same way.
CREATE OR REPLACE MACRO channel_group(src, med) AS
  CASE
    WHEN src IS NULL AND med IS NULL                                         THEN 'Unassigned'
    WHEN med IN ('<Other>', '(data deleted)') OR src IN ('<Other>', '(data deleted)')
                                                                             THEN 'Obfuscated'
    WHEN src = '(direct)' AND med IN ('(none)', '(not set)')                 THEN 'Direct'
    WHEN lower(med) = 'organic'                                              THEN 'Organic Search'
    WHEN lower(med) IN ('cpc', 'ppc', 'paidsearch', 'paid')                  THEN 'Paid Search'
    WHEN lower(med) IN ('display', 'cpm', 'banner')                          THEN 'Display'
    WHEN lower(med) = 'email'                                                THEN 'Email'
    WHEN lower(med) IN ('social', 'social-network', 'sm')                    THEN 'Organic Social'
    WHEN lower(med) = 'affiliate'                                            THEN 'Affiliates'
    WHEN lower(med) = 'referral'                                             THEN 'Referral'
    ELSE 'Other'
  END;
