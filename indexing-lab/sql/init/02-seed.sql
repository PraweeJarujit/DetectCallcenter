-- ใส่ข้อมูล 1,000,000 rows (ย้อนหลัง 365 วันจาก 2026-09-25)
-- setseed() ทำให้ข้อมูลทั้ง 2 database เหมือนกันทุก row
\echo '>>> Seeding 1,000,000 rows ... (ประมาณ 10-40 วินาที)'
SELECT setseed(0.42) \gset

INSERT INTO transactions (transaction_date, customer_id, amount, status, description)
SELECT DATE '2025-09-25' + (random() * 365)::int,
       (random() * 9999 + 1)::int,
       round((random() * 10000)::numeric, 2),
       (ARRAY['paid', 'paid', 'paid', 'pending', 'cancelled'])[1 + floor(random() * 5)::int],
       'txn-' || g
FROM generate_series(1, 1000000) AS g;

ANALYZE transactions;
\echo '>>> Seed done'
