-- LAB 04: มี index แต่ไม่ถูกใช้ — กับ query ของโปรเจกต์เราเอง (รันบน pg_app_with_index)
-- ให้ "ทาย" ก่อนรันแต่ละข้อว่าจะได้ Seq Scan หรือ Index Scan
\timing on

\echo '\n===== 4.1 ❌ ครอบ column ด้วย function: "สายวันนี้" แบบเขียนผิด ====='
EXPLAIN ANALYZE
SELECT count(*) FROM call_logs WHERE date(timezone('Asia/Bangkok', created_at)) = '2026-10-02';
\echo '===== 4.1 ✅ เขียนเป็นช่วงเวลา (แบบที่ /calls/stats ใช้จริง) ====='
EXPLAIN ANALYZE
SELECT count(*) FROM call_logs WHERE created_at >= '2026-10-02 00:00+07';

\echo '\n===== 4.2 ⚠️ partial index ใช้ได้เฉพาะเงื่อนไขที่ "อยู่ใน" predicate (risk_score >= 80) ====='
EXPLAIN ANALYZE   -- >= 90 เป็นสับเซตของ >= 80 -> ใช้ partial index ได้
SELECT count(*) FROM call_logs WHERE created_at >= '2026-10-02 00:00+07' AND risk_score >= 90;
EXPLAIN ANALYZE   -- >= 79 กว้างกว่า predicate -> ใช้ partial index ไม่ได้ (ต้องไปใช้ IDX-6 แล้วกรอง risk ทีละแถว)
SELECT count(*) FROM call_logs WHERE created_at >= '2026-10-02 00:00+07' AND risk_score >= 79;

\echo '\n===== 4.3 LIKE prefix: btree ธรรมดา (collation en_US) vs varchar_pattern_ops (IDX-1) ====='
BEGIN;
DROP INDEX uq_blacklist_numbers_phone;
CREATE UNIQUE INDEX uq_phone_plain ON blacklist_numbers (phone_number);   -- btree ปกติ
EXPLAIN ANALYZE SELECT * FROM blacklist_numbers WHERE phone_number LIKE '08123%';   -- ❌ Seq Scan
EXPLAIN ANALYZE SELECT * FROM blacklist_numbers WHERE phone_number = '0812345678';  -- ✅ ใช้ได้เฉพาะ =
ROLLBACK;  -- คืน IDX-1
EXPLAIN ANALYZE SELECT * FROM blacklist_numbers WHERE phone_number LIKE '08123%';   -- ✅ IDX-1
EXPLAIN ANALYZE SELECT * FROM blacklist_numbers WHERE phone_number LIKE '%5678';    -- ❌ ขึ้นต้นด้วย % ใช้ index ไม่ได้

\echo '\n===== 4.4 ❌ index บน status อย่างเดียว (มีแค่ 3 ค่า) vs composite IDX-2 ====='
SELECT status, count(*), round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct FROM blacklist_numbers GROUP BY 1;
BEGIN;
DROP INDEX ix_blacklist_numbers_status_risk;                 -- ปิด IDX-2 และ IDX-3 ชั่วคราว
DROP INDEX ix_blacklist_numbers_risk;
CREATE INDEX idx_bl_status_only ON blacklist_numbers (status);
ANALYZE blacklist_numbers;
-- query จริงของ GET /blacklist?status=high_risk : index เดี่ยวต้องดึง ~67,000 แถวแล้ว Sort เพื่อเอาแค่ 20
EXPLAIN ANALYZE SELECT * FROM blacklist_numbers WHERE status = 'high_risk' ORDER BY risk_score DESC, id LIMIT 20;
ROLLBACK;
-- ✅ composite (status, risk_score DESC, id): อ่าน 20 entry แรกของกลุ่ม high_risk แล้วหยุดเลย
EXPLAIN ANALYZE SELECT * FROM blacklist_numbers WHERE status = 'high_risk' ORDER BY risk_score DESC, id LIMIT 20;

\echo '\n===== 4.5 OFFSET ลึก vs Keyset pagination (/calls/logs?before_id=) ====='
-- หา cursor = แถวที่ 100,000 (จำลองว่า client ส่ง before_id มา) เก็บลงตัวแปร psql :c_at / :c_id
SELECT created_at AS c_at, id AS c_id FROM call_logs ORDER BY created_at DESC, id DESC OFFSET 100000 LIMIT 1 \gset
EXPLAIN ANALYZE   -- ❌ OFFSET: ต้องอ่านแล้วทิ้ง 100,000 แถวทุกครั้ง (ยิ่งหน้าลึกยิ่งช้า)
SELECT * FROM call_logs ORDER BY created_at DESC, id DESC OFFSET 100000 LIMIT 20;
EXPLAIN ANALYZE   -- ✅ Keyset: กระโดดไปตำแหน่ง cursor ใน IDX-6 ทันที (หน้าไหนก็เร็วเท่ากัน)
SELECT * FROM call_logs
WHERE (created_at, id) < (:'c_at', :c_id)
ORDER BY created_at DESC, id DESC LIMIT 20;
