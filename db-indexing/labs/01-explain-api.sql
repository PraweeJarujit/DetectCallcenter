-- LAB 01: query จริงของ API — รันบนทั้ง 2 database แล้วเทียบ plan + เวลา
-- "วันนี้" ของ lab = 2026-10-02 (เวลาไทย)
\timing on

\echo '\n===== Q8  GET /calls/stats : จำนวนสายวันนี้ (IDX-6) ====='
EXPLAIN ANALYZE
SELECT count(*) FROM call_logs WHERE created_at >= '2026-10-02 00:00+07';

\echo '\n===== Q9  GET /calls/stats : สายเสี่ยงสูงวันนี้ (IDX-7 partial) ====='
EXPLAIN ANALYZE
SELECT count(*) FROM call_logs WHERE created_at >= '2026-10-02 00:00+07' AND risk_score >= 80;

\echo '\n===== Q10 GET /calls/trend : สายเสี่ยงสูงรายวัน 7 วัน (IDX-7) ====='
EXPLAIN ANALYZE
SELECT date(timezone('Asia/Bangkok', created_at)) AS d, count(*)
FROM call_logs
WHERE created_at >= '2026-09-26 00:00+07' AND risk_score >= 80
GROUP BY 1;

\echo '\n===== Q11 GET /calls/logs : 20 แถวล่าสุด (IDX-6, ไม่ต้อง Sort) ====='
EXPLAIN ANALYZE
SELECT * FROM call_logs ORDER BY created_at DESC, id DESC LIMIT 21;

\echo '\n===== Q3  GET /blacklist?status=high_risk (IDX-2) ====='
EXPLAIN ANALYZE
SELECT * FROM blacklist_numbers WHERE status = 'high_risk' ORDER BY risk_score DESC, id LIMIT 20;

\echo '\n===== Q5  GET /blacklist/{phone} : report ล่าสุดของเบอร์ (IDX-4) ====='
EXPLAIN ANALYZE
SELECT r.* FROM reports r
JOIN blacklist_numbers b ON b.id = r.blacklist_number_id
WHERE b.phone_number = (SELECT phone_number FROM blacklist_numbers ORDER BY report_count DESC, phone_number LIMIT 1)
ORDER BY r.created_at DESC LIMIT 50;

\echo '\n===== Q6  GET /reports/me (IDX-5) ====='
EXPLAIN ANALYZE
SELECT * FROM reports
WHERE reported_by = (SELECT id FROM users WHERE username = 'user7')
ORDER BY created_at DESC LIMIT 20;
