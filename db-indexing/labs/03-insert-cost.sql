-- LAB 03: ต้นทุน INSERT เมื่อมี index (รันทั้ง 2 database แล้วเทียบเวลา) — ROLLBACK ข้อมูลไม่เพิ่มจริง
-- call_logs เป็นตารางที่ insert บ่อยที่สุด (ทุกครั้งที่ตรวจเบอร์) มี index 3 ตัว + PK
\timing on
BEGIN;
INSERT INTO call_logs (phone_number, risk_score, status, is_synthetic_voice, source, created_at)
SELECT '08' || lpad(floor(random() * 100000000)::text, 8, '0'),
       s, CASE WHEN s >= 80 THEN 'high_risk' WHEN s >= 50 THEN 'suspect' ELSE 'safe' END,
       false, 'number_check', now()
FROM (SELECT floor(random() * 100)::int AS s FROM generate_series(1, 200000)) x;
ROLLBACK;
-- คำถาม: ช้าลงกี่ % ? คุ้มไหมเมื่อเทียบกับ dashboard ที่เร็วขึ้นหลักร้อย-หมื่นเท่า (ดู results/benchmark.md)
