-- LAB 06: Workshop  (ทำบน pg_with_index — index ที่สร้างเองให้ DROP ท้ายงาน)
-- โจทย์ 1: query นี้ช้า ให้ออกแบบ index แล้วพิสูจน์ด้วย EXPLAIN ANALYZE ก่อน/หลัง
EXPLAIN ANALYZE
SELECT transaction_date, sum(amount)
FROM transactions
WHERE status = 'pending' AND transaction_date >= '2026-09-01'
GROUP BY transaction_date
ORDER BY transaction_date;

-- โจทย์ 2: ลูกค้า 5 อันดับที่ยอดสูงสุดในเดือน 2026-08
--           เขียน query เอง แล้วบอกว่า index ตัวไหนถูกใช้

-- โจทย์ 3: แก้ query ด้านล่างให้ใช้ index ได้ (ห้ามสร้าง index เพิ่ม)
EXPLAIN ANALYZE
SELECT * FROM transactions
WHERE to_char(transaction_date, 'YYYY-MM') = '2026-08';
