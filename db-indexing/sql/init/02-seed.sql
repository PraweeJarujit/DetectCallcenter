-- =====================================================================
-- ข้อมูลจำลองขนาด production ของ VoiceGuard (ทั้ง 2 database ได้ข้อมูลเหมือนกันทุก row: setseed)
--   users                1,000
--   blacklist_numbers  200,000
--   reports            600,000   (+ report_categories ~900,000)
--   call_logs        2,000,000   (ย้อนหลัง 365 วัน ถึง 2026-10-02 เวลาไทย)
--   emergency_contacts   2,000 / token_blacklist 50,000
-- "วันนี้" ของ lab = 2026-10-02 (Asia/Bangkok) — ทุก query ใน labs/ อ้างวันนี้
-- =====================================================================
\echo '>>> Seeding VoiceGuard data ... (ประมาณ 1-3 นาที)'
SET client_min_messages = warning;
SELECT setseed(0.42) \gset

-- ---------- users ----------
INSERT INTO users (id, username, email, hashed_password, full_name, role, is_active, auto_notify, created_at, updated_at)
SELECT gen_random_uuid(), 'user' || g, 'user' || g || '@example.com', 'not-a-real-hash', 'ผู้ใช้ ' || g,
       (ARRAY['gov', 'bank', 'telco', 'gov'])[1 + (g % 4)], true, true,
       TIMESTAMPTZ '2025-10-02 00:00+07' + (g || ' minutes')::interval,
       TIMESTAMPTZ '2025-10-02 00:00+07' + (g || ' minutes')::interval
FROM generate_series(1, 1000) g;

CREATE TEMP TABLE u AS SELECT id, row_number() OVER (ORDER BY username) AS rn FROM users;
CREATE UNIQUE INDEX ON u (rn);

-- ---------- blacklist_numbers (เบอร์ไม่ซ้ำ: g*7919 mod 1e8 เป็น one-to-one เพราะ 7919 เป็นจำนวนเฉพาะ) ----------
INSERT INTO blacklist_numbers (id, phone_number, status, risk_score, report_count, first_reported_at, last_reported_at)
SELECT gen_random_uuid(),
       '0' || (ARRAY['6', '8', '9'])[1 + (g % 3)] || lpad(((g::bigint * 7919) % 100000000)::text, 8, '0'),
       CASE WHEN s >= 80 THEN 'high_risk' WHEN s >= 50 THEN 'suspect' ELSE 'safe' END,
       s, 0, t, t
FROM (
  SELECT g, (40 + floor(random() * 60))::int AS s,
         TIMESTAMPTZ '2026-10-02 23:59+07' - random() * INTERVAL '365 days' AS t
  FROM generate_series(1, 200000) g
) x;

CREATE TEMP TABLE b AS SELECT id, row_number() OVER (ORDER BY phone_number) AS rn FROM blacklist_numbers;
CREATE UNIQUE INDEX ON b (rn);

-- ---------- reports (10% ไม่มีผู้แจ้ง = user ถูกลบไปแล้ว) ----------
INSERT INTO reports (id, blacklist_number_id, reported_by, risk_score, note, created_at)
SELECT gen_random_uuid(), b.id, u.id, r.score, 'seed report ' || r.g, r.t
FROM (
  SELECT g, 1 + floor(random() * 200000)::int AS bn, 1 + floor(random() * 1100)::int AS un,
         (40 + floor(random() * 60))::int AS score,
         TIMESTAMPTZ '2026-10-02 23:59+07' - random() * INTERVAL '365 days' AS t
  FROM generate_series(1, 600000) g
) r
JOIN b ON b.rn = r.bn
LEFT JOIN u ON u.rn = r.un;          -- un > 1000 -> NULL (~10%)

-- 1-2 หมวดต่อ report (Many-to-Many)
INSERT INTO report_categories (report_id, category_id)
SELECT id, 1 + floor(random() * 8)::int FROM reports;
INSERT INTO report_categories (report_id, category_id)
SELECT id, 1 + floor(random() * 8)::int FROM reports WHERE random() < 0.5
ON CONFLICT DO NOTHING;

-- ค่าสรุปใน blacklist_numbers ให้ตรงกับ reports
UPDATE blacklist_numbers bn SET report_count = x.n, last_reported_at = x.last_at
FROM (SELECT blacklist_number_id, count(*) n, max(created_at) last_at FROM reports GROUP BY 1) x
WHERE x.blacklist_number_id = bn.id;

-- ---------- call_logs: insert เรียงตามเวลา (id เพิ่มตามเวลา เหมือนระบบจริง) ----------
INSERT INTO call_logs (phone_number, user_id, risk_score, status, is_synthetic_voice, source, created_at)
SELECT phone, uid, score,
       CASE WHEN score >= 80 THEN 'high_risk' WHEN score >= 50 THEN 'suspect' ELSE 'safe' END,
       score >= 80 AND random() < 0.7,
       (ARRAY['number_check', 'number_check', 'audio', 'demo'])[1 + floor(random() * 4)::int],
       t
FROM (
  SELECT '08' || lpad(floor(random() * 100000000)::text, 8, '0') AS phone,
         CASE WHEN random() < 0.5 THEN (SELECT id FROM u WHERE u.rn = 1 + (g % 1000)) END AS uid,
         CASE WHEN r < 0.6 THEN floor(random() * 50)::int
              WHEN r < 0.8 THEN (50 + floor(random() * 30))::int
              ELSE (80 + floor(random() * 20))::int END AS score,
         TIMESTAMPTZ '2026-10-02 23:59:59+07' - random() * INTERVAL '365 days' AS t
  FROM (SELECT g, random() AS r FROM generate_series(1, 2000000) g) s
) c
ORDER BY t;

-- ---------- emergency_contacts / token_blacklist ----------
INSERT INTO emergency_contacts (id, user_id, name, phone_number)
SELECT gen_random_uuid(), u.id, 'ผู้ติดต่อ ' || k, '08' || lpad((u.rn * 10 + k)::text, 8, '0')
FROM u CROSS JOIN generate_series(1, 2) k;

INSERT INTO token_blacklist (id, jti, expires_at, revoked_at)
SELECT gen_random_uuid(), md5(g::text), now() + INTERVAL '1 hour', now() FROM generate_series(1, 50000) g;

VACUUM ANALYZE;
\echo '>>> Seed done'
