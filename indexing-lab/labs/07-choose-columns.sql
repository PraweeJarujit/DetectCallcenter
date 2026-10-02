-- LAB 07: เลือก column ไหนทำ index / ทำไมไม่ทำทุก column
-- รันบน pg_with_index (port 5432)  DBeaver: เลือกทั้งไฟล์แล้ว Alt+X

-- STEP 1: ความหลากหลายของค่า (Cardinality)
SELECT count(DISTINCT customer_id)      AS customer_id,
       count(DISTINCT transaction_date) AS transaction_date,
       count(DISTINCT status)           AS status
FROM transactions;

-- STEP 2: INSERT ตอนมี index 2 ตัว (จดเวลา ~1.3 วินาที)
BEGIN;
INSERT INTO transactions (transaction_date, customer_id, amount, status, description)
SELECT DATE '2025-09-25' + (random()*365)::int, (random()*9999+1)::int,
       round((random()*10000)::numeric, 2), 'paid', 'bulk-' || g
FROM generate_series(1, 200000) g;
ROLLBACK;

-- STEP 3: ทำ index "ทุก column" แล้ว INSERT ซ้ำ (~2.3 วินาที) — ROLLBACK คืนค่าเอง
BEGIN;
CREATE INDEX idx_tx_amount ON transactions (amount);
CREATE INDEX idx_tx_status ON transactions (status);
CREATE INDEX idx_tx_desc   ON transactions (description);

SELECT pg_size_pretty(pg_indexes_size('transactions'))  AS index_size,
       pg_size_pretty(pg_relation_size('transactions')) AS table_size;

INSERT INTO transactions (transaction_date, customer_id, amount, status, description)
SELECT DATE '2025-09-25' + (random()*365)::int, (random()*9999+1)::int,
       round((random()*10000)::numeric, 2), 'paid', 'bulk-' || g
FROM generate_series(1, 200000) g;
ROLLBACK;

-- STEP 4: index ไหนไม่เคยถูกใช้
SELECT indexrelname AS index_name, idx_scan AS times_used,
       pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
ORDER BY idx_scan;
