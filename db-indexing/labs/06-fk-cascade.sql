-- LAB 06: Foreign key ไม่มี index อัตโนมัติใน Postgres -> ลบแถวแม่ช้า (รันบน pg_app_with_index)
-- ดูบรรทัด "Trigger for constraint ..." ใน EXPLAIN ANALYZE: เวลาที่ใช้ตามลบ/ตั้ง NULL ในตารางลูก
\timing on
-- เลือกเบอร์ที่ถูกแจ้งมากที่สุดเก็บไว้ในตัวแปร :bl_id (psql) จะได้ไม่ปนเวลาค้นหาลงในผล DELETE
SELECT id AS bl_id FROM blacklist_numbers ORDER BY report_count DESC, phone_number LIMIT 1 \gset

\echo '\n===== ✅ มี IDX-4: ลบเบอร์ -> CASCADE ลบ reports ของเบอร์นั้น ====='
BEGIN;
EXPLAIN ANALYZE DELETE FROM blacklist_numbers WHERE id = :'bl_id';
ROLLBACK;

\echo '\n===== ❌ ไม่มี IDX-4: trigger ต้อง Seq Scan reports 600,000 แถว ====='
BEGIN;
DROP INDEX ix_reports_blacklist_created;
EXPLAIN ANALYZE DELETE FROM blacklist_numbers WHERE id = :'bl_id';
ROLLBACK;

\echo '\n===== ✅ ลบ user -> SET NULL ใน reports + call_logs และ CASCADE contacts (มี IDX-5/8/9) ====='
BEGIN;
EXPLAIN ANALYZE DELETE FROM users WHERE username = 'user7';
ROLLBACK;

\echo '\n===== ❌ ลบ user โดยไม่มี IDX-8: trigger ต้อง Seq Scan call_logs 2 ล้านแถว ====='
BEGIN;
DROP INDEX ix_call_logs_user_created;
EXPLAIN ANALYZE DELETE FROM users WHERE username = 'user7';
ROLLBACK;
