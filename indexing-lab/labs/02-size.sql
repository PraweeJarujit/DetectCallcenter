-- LAB 02: index ใช้พื้นที่เท่าไร
SELECT pg_size_pretty(pg_relation_size('transactions'))       AS table_size,
       pg_size_pretty(pg_indexes_size('transactions'))        AS index_size,
       pg_size_pretty(pg_total_relation_size('transactions')) AS total_size;

-- รายละเอียดแต่ละ index
SELECT indexrelname AS index_name,
       pg_size_pretty(pg_relation_size(indexrelid)) AS size,
       idx_scan AS times_used
FROM pg_stat_user_indexes
WHERE relname = 'transactions'
ORDER BY pg_relation_size(indexrelid) DESC;
