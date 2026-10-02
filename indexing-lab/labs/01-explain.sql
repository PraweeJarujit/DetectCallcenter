-- LAB 01: เทียบ query plan และเวลา  (รันบนทั้ง 2 database แล้วเทียบกัน)
\timing on
\echo '\n===== Test 1: Exact match วันที่ ====='
EXPLAIN ANALYZE
SELECT * FROM transactions WHERE transaction_date = '2026-09-10';

\echo '\n===== Test 2: หาตามลูกค้า ====='
EXPLAIN ANALYZE
SELECT * FROM transactions WHERE customer_id = 42;

\echo '\n===== Test 3: Range แคบ (7 วัน ≈ 2%) ====='
EXPLAIN ANALYZE
SELECT * FROM transactions
WHERE transaction_date BETWEEN '2026-09-01' AND '2026-09-07';

\echo '\n===== Test 4: Range กว้าง (6 เดือน ≈ 50%) — index ยังช่วยไหม? ====='
EXPLAIN ANALYZE
SELECT * FROM transactions
WHERE transaction_date BETWEEN '2026-03-01' AND '2026-08-31';

\echo '\n===== Test 5: COUNT ต่อวัน (ลอง Index Only Scan) ====='
VACUUM transactions;
EXPLAIN ANALYZE
SELECT count(*) FROM transactions WHERE transaction_date = '2026-09-10';
