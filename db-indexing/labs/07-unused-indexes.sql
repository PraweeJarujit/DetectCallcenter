-- LAB 07: ตรวจว่า index ไหน "ไม่เคยถูกใช้" (รันบน pg_app_with_index หลังลองใช้ระบบ/รัน lab อื่นแล้ว)
-- index ที่ idx_scan = 0 นาน ๆ คือภาระฟรี: กินพื้นที่ + ทำให้ INSERT/UPDATE ช้า -> พิจารณา DROP
SELECT relname AS table_name, indexrelname AS index_name, idx_scan AS times_used,
       pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
ORDER BY idx_scan, pg_relation_size(indexrelid) DESC;

-- ทำไมไม่ทำ index ทุก column? ดู cardinality (จำนวนค่าไม่ซ้ำ) ของ call_logs
SELECT count(DISTINCT status)       AS status,
       count(DISTINCT source)       AS source,
       count(DISTINCT risk_score)   AS risk_score,
       count(DISTINCT phone_number) AS phone_number,
       count(DISTINCT user_id)      AS user_id
FROM call_logs;
-- status/source ค่าซ้ำเยอะ -> index เดี่ยวไม่ช่วย (lab 04 ข้อ 4.4)
-- phone_number ค่าไม่ซ้ำสูง แต่ "ไม่มี API ไหนค้น call_logs ด้วยเบอร์" -> ไม่ทำ (ทำเมื่อมี query จริงเท่านั้น)
