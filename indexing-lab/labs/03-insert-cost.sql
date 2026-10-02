-- LAB 03: ต้นทุน INSERT เมื่อมี index  (รันทั้ง 2 database แล้วเทียบเวลา)
-- ใช้ ROLLBACK ข้อมูลจึงไม่เพิ่มจริง รันซ้ำได้
\timing on
BEGIN;
INSERT INTO transactions (transaction_date, customer_id, amount, status, description)
SELECT DATE '2025-09-25' + (random() * 365)::int,
       (random() * 9999 + 1)::int,
       round((random() * 10000)::numeric, 2),
       'paid',
       'bulk-' || g
FROM generate_series(1, 200000) AS g;
ROLLBACK;
