-- LAB 05: Composite index และ Leftmost rule  (รันบน pg_with_index)
\timing on

-- ปิด index เดี่ยวชั่วคราว (ใน transaction) เพื่อดูผลของ composite อย่างเดียว
BEGIN;
DROP INDEX idx_tx_customer;
DROP INDEX idx_tx_date;
CREATE INDEX idx_cust_date ON transactions (customer_id, transaction_date);
ANALYZE transactions;

\echo '\n===== ✅ ใช้ column ซ้ายสุด ====='
EXPLAIN ANALYZE SELECT * FROM transactions WHERE customer_id = 42;

\echo '\n===== ✅ ใช้ครบทั้ง 2 column ====='
EXPLAIN ANALYZE SELECT * FROM transactions
WHERE customer_id = 42 AND transaction_date >= '2026-06-01';

\echo '\n===== ⚠️ ข้าม column ซ้ายสุด ====='
EXPLAIN ANALYZE SELECT * FROM transactions WHERE transaction_date = '2026-09-10';

\echo '\n===== ✅ ORDER BY + LIMIT ตรงกับลำดับ index (ไม่ต้อง Sort) ====='
EXPLAIN ANALYZE SELECT * FROM transactions
WHERE customer_id = 42 ORDER BY transaction_date DESC LIMIT 10;

ROLLBACK;  -- คืน index เดิมทั้งหมด
