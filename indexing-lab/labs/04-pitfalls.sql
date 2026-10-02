-- LAB 04: มี index แต่ไม่ถูกใช้  (รันบน pg_with_index)
-- ให้นิสิต "ทาย" ก่อนรันแต่ละข้อว่าจะได้ Seq Scan หรือ Index Scan
\timing on

\echo '\n===== 4.1 ❌ ครอบ column ด้วย function ====='
EXPLAIN ANALYZE
SELECT count(*) FROM transactions
WHERE EXTRACT(MONTH FROM transaction_date) = 9 AND EXTRACT(DAY FROM transaction_date) = 10;

\echo '\n===== 4.1 ✅ เขียนเป็นเงื่อนไขตรงๆ ====='
EXPLAIN ANALYZE
SELECT count(*) FROM transactions
WHERE transaction_date = '2026-09-10';

\echo '\n===== 4.2 ❌ คำนวณบน column ====='
EXPLAIN ANALYZE
SELECT * FROM transactions WHERE customer_id + 0 = 42;

\echo '\n===== 4.3 LIKE: ขึ้นต้นด้วยคำ vs ขึ้นต้นด้วย % (สร้าง index ชั่วคราวบน description) ====='
CREATE INDEX IF NOT EXISTS idx_tx_desc ON transactions (description varchar_pattern_ops);
EXPLAIN ANALYZE SELECT * FROM transactions WHERE description LIKE 'txn-12345%';
EXPLAIN ANALYZE SELECT * FROM transactions WHERE description LIKE '%12345';
DROP INDEX idx_tx_desc;

\echo '\n===== 4.4 ❌ column ค่าซ้ำเยอะ (status มีแค่ 3 ค่า) ====='
CREATE INDEX IF NOT EXISTS idx_tx_status ON transactions (status);
ANALYZE transactions;
EXPLAIN ANALYZE SELECT * FROM transactions WHERE status = 'paid';       -- ~60%
EXPLAIN ANALYZE SELECT * FROM transactions WHERE status = 'cancelled';  -- ~20%
DROP INDEX idx_tx_status;
