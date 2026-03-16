-- =============================================================================
-- sql_queries.sql  —  Portfolio-grade SQL for the Citizen Sensor Tracker
-- Target: db/citizen_sensor.db  (SQLite)
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- 1.  DAILY CORRELATION: complaints vs. PM2.5 by sensor
--     Shows each sensor-day with both metrics side by side.
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    sr.sensor_name,
    sr.date,
    sr.pm25_mean,
    COALESCE(cd.complaint_count, 0) AS complaint_count
FROM sensor_readings sr
LEFT JOIN (
    SELECT nearest_sensor, date, COUNT(*) AS complaint_count
    FROM complaints
    GROUP BY nearest_sensor, date
) cd
    ON sr.sensor_name = cd.nearest_sensor
   AND sr.date        = cd.date
ORDER BY sr.sensor_name, sr.date;


-- ─────────────────────────────────────────────────────────────────────────────
-- 2.  SPIKE DETECTION: PM2.5 spikes and nearby complaints within ±2 days
--     Uses a CTE to identify spike days (PM2.5 > 35 µg/m³, EPA 24-hr
--     standard for "Unhealthy for Sensitive Groups"), then counts
--     complaints in a ±2-day window around each spike.
-- ─────────────────────────────────────────────────────────────────────────────
WITH spike_days AS (
    SELECT sensor_name, date, pm25_mean
    FROM sensor_readings
    WHERE pm25_mean > 35.0
),
complaint_window AS (
    SELECT
        s.sensor_name,
        s.date        AS spike_date,
        s.pm25_mean,
        c.date        AS complaint_date,
        c.complaint_id
    FROM spike_days s
    LEFT JOIN complaints c
        ON c.nearest_sensor = s.sensor_name
       AND c.date BETWEEN DATE(s.date, '-2 days') AND DATE(s.date, '+2 days')
)
SELECT
    sensor_name,
    spike_date,
    pm25_mean,
    COUNT(DISTINCT complaint_id)   AS complaints_within_2d,
    MIN(complaint_date)            AS earliest_complaint,
    MAX(complaint_date)            AS latest_complaint,
    CASE
        WHEN COUNT(complaint_id) > 0 THEN 'CONCORDANT'
        ELSE 'MISSED_SPIKE'
    END AS concordance
FROM complaint_window
GROUP BY sensor_name, spike_date, pm25_mean
ORDER BY pm25_mean DESC;


-- ─────────────────────────────────────────────────────────────────────────────
-- 3.  NEIGHBORHOOD RANKING: complaint-to-reading ratio by sensor area
--     Which sensor areas generate the most complaints relative to how
--     many days of data we have?
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    d.sensor_name,
    ROUND(AVG(d.pm25_mean), 1)               AS avg_pm25,
    SUM(d.complaint_count)                    AS total_complaints,
    COUNT(*)                                  AS total_days,
    ROUND(1.0 * SUM(d.complaint_count)
          / COUNT(*), 4)                      AS complaints_per_day,
    ROUND(AVG(d.lat), 4)                      AS lat,
    ROUND(AVG(d.lon), 4)                      AS lon
FROM daily_merged d
GROUP BY d.sensor_name
HAVING total_complaints > 0
ORDER BY complaints_per_day DESC
LIMIT 20;


-- ─────────────────────────────────────────────────────────────────────────────
-- 4.  TEMPORAL PATTERN: day-of-week complaint counts vs. avg PM2.5
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    c.day_of_week,
    COUNT(*)                             AS total_complaints,
    ROUND(AVG(sr.pm25_mean), 2)          AS avg_pm25_on_complaint_days
FROM complaints c
JOIN sensor_readings sr
    ON sr.sensor_name = c.nearest_sensor
   AND sr.date        = c.date
GROUP BY c.day_of_week
ORDER BY
    CASE c.day_of_week
        WHEN 'Monday'    THEN 1
        WHEN 'Tuesday'   THEN 2
        WHEN 'Wednesday' THEN 3
        WHEN 'Thursday'  THEN 4
        WHEN 'Friday'    THEN 5
        WHEN 'Saturday'  THEN 6
        WHEN 'Sunday'    THEN 7
    END;


-- ─────────────────────────────────────────────────────────────────────────────
-- 5.  FALSE ALARMS: complaint days where PM2.5 was actually low
--     Identifies complaints on days when PM2.5 was below the EPA annual
--     standard (12 µg/m³) — potential false alarms or non-PM2.5 odor issues.
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    c.complaint_id,
    c.date,
    c.nearest_sensor,
    c.distance_to_sensor_m,
    sr.pm25_mean,
    c.complaint_detail,
    c.address
FROM complaints c
JOIN sensor_readings sr
    ON sr.sensor_name = c.nearest_sensor
   AND sr.date        = c.date
WHERE sr.pm25_mean < 12.0
ORDER BY sr.pm25_mean ASC
LIMIT 25;


-- ─────────────────────────────────────────────────────────────────────────────
-- 6.  WEEKLY TREND: rolling weekly aggregation across entire city
-- ─────────────────────────────────────────────────────────────────────────────
WITH weekly AS (
    SELECT
        -- ISO week start (Monday)
        DATE(date, 'weekday 1', '-7 days') AS week_start,
        ROUND(AVG(pm25_mean), 2)           AS avg_pm25,
        SUM(complaint_count)               AS total_complaints,
        COUNT(DISTINCT sensor_name)        AS active_sensors
    FROM daily_merged
    GROUP BY week_start
)
SELECT *
FROM weekly
ORDER BY week_start;


-- ─────────────────────────────────────────────────────────────────────────────
-- 7.  LEAD-LAG: average complaints on days before/after a PM2.5 spike
--     Uses the pre-computed lag/lead columns from the merged table.
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    'Day of spike'   AS period,
    ROUND(AVG(complaint_count), 3)  AS avg_complaints,
    COUNT(*)                        AS n_spike_days
FROM daily_merged
WHERE pm25_spike = 1

UNION ALL

SELECT
    'Day before spike',
    ROUND(AVG(dm2.complaint_count), 3),
    COUNT(*)
FROM daily_merged dm1
JOIN daily_merged dm2
    ON dm2.sensor_name = dm1.sensor_name
   AND dm2.date = DATE(dm1.date, '-1 day')
WHERE dm1.pm25_spike = 1

UNION ALL

SELECT
    'Day after spike',
    ROUND(AVG(dm2.complaint_count), 3),
    COUNT(*)
FROM daily_merged dm1
JOIN daily_merged dm2
    ON dm2.sensor_name = dm1.sensor_name
   AND dm2.date = DATE(dm1.date, '+1 day')
WHERE dm1.pm25_spike = 1;
