-- LAB 05: Composite index + Leftmost rule บนตาราง blacklist_numbers (รันบน pg_app_with_index)
\timing on
BEGIN;
DROP INDEX ix_blacklist_numbers_risk;   -- เหลือแค่ IDX-2 (status, risk_score DESC, id) ชั่วคราว

\echo '\n===== ✅ มี status (column ซ้ายสุด) + ORDER BY ตรงลำดับ index -> ไม่มี Sort ====='
EXPLAIN ANALYZE SELECT * FROM blacklist_numbers
WHERE status = 'suspect' ORDER BY risk_score DESC, id LIMIT 20;

\echo '\n===== ⚠️ ไม่มี status (ข้าม column ซ้ายสุด) -> ใช้ IDX-2 ไม่ได้ ต้อง Sort ทั้งตาราง ====='
EXPLAIN ANALYZE SELECT * FROM blacklist_numbers ORDER BY risk_score DESC, id LIMIT 20;

\echo '\n===== ⚠️ ORDER BY ทิศทางไม่ตรง index (risk_score ASC, id DESC) ====='
EXPLAIN ANALYZE SELECT * FROM blacklist_numbers
WHERE status = 'suspect' ORDER BY risk_score ASC, id ASC LIMIT 20;
-- (risk ASC, id DESC = กลับด้านทั้งคู่ของ index -> Index Scan Backward ได้; แต่ ASC, ASC ไม่ได้)

ROLLBACK;  -- คืน IDX-3

\echo '\n===== ✅ หลังคืน IDX-3: หน้า Blacklist แบบไม่กรอง ====='
EXPLAIN ANALYZE SELECT * FROM blacklist_numbers ORDER BY risk_score DESC, id LIMIT 20;
