-- LAB 01b: สร้าง index เอง + Demo ลูกค้า 100 คน
-- รันบน pg_no_index (port 5433) ทีละ step ใน DBeaver (Ctrl+Enter / Ctrl+Shift+E)

-- STEP 2: Demo ลูกค้า 100 คนเปิดหน้า "ประวัติการซื้อ" (ก่อนมี index ~8 วินาที)
SELECT count(*) AS lookups, sum(x.n) AS rows_found
FROM generate_series(1, 100) AS c(id)
CROSS JOIN LATERAL (
  SELECT count(*) AS n FROM transactions t WHERE t.customer_id = c.id
) x;

-- STEP 3: ดูสาเหตุ (Ctrl+Shift+E ติ๊ก Analyze) → Parallel Seq Scan
SELECT * FROM transactions WHERE customer_id = 42;

-- STEP 4: สร้าง index
CREATE INDEX idx_tx_customer ON transactions (customer_id);

-- STEP 5: Explain STEP 3 ซ้ำ → Bitmap Index Scan
-- STEP 6: รัน STEP 2 ซ้ำ → ~0.003 วินาที

-- STEP 7: ลบ index คืนสภาพ (ห้ามลืม)
DROP INDEX idx_tx_customer;
