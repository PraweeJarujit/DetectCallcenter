-- LAB 02: index ใช้พื้นที่เท่าไร (รันทั้ง 2 database)
SELECT relname AS table_name,
       pg_size_pretty(pg_relation_size(relid))       AS table_size,
       pg_size_pretty(pg_indexes_size(relid))        AS index_size,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC;

-- รายละเอียดแต่ละ index — สังเกต partial index (IDX-7) เล็กกว่า IDX-6 ราว 5 เท่า
-- เพราะเก็บเฉพาะแถว risk_score >= 80 (~20% ของ call_logs)
SELECT relname AS table_name, indexrelname AS index_name,
       pg_size_pretty(pg_relation_size(indexrelid)) AS size,
       idx_scan AS times_used
FROM pg_stat_user_indexes
ORDER BY relname, pg_relation_size(indexrelid) DESC;
