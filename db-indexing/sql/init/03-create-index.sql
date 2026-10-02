-- =====================================================================
-- Index เพื่อ performance (เหมือน Alembic migration 0002) — เฉพาะ pg_app_with_index
-- เหตุผลของแต่ละตัวอยู่ใน db-indexing/README.md (ตาราง IDX-1 ถึง IDX-9)
-- =====================================================================
\echo '>>> Creating performance indexes ...'
-- blacklist_numbers: หน้า Blacklist เรียงตาม risk (มี/ไม่มี filter status)
CREATE INDEX ix_blacklist_numbers_status_risk ON blacklist_numbers (status, risk_score DESC, id);   -- IDX-2
CREATE INDEX ix_blacklist_numbers_risk        ON blacklist_numbers (risk_score DESC, id);           -- IDX-3
-- reports: FK ไม่มี index อัตโนมัติใน Postgres
CREATE INDEX ix_reports_blacklist_created ON reports (blacklist_number_id, created_at DESC);         -- IDX-4
CREATE INDEX ix_reports_reporter_created  ON reports (reported_by, created_at DESC);                 -- IDX-5
-- report_categories: ค้นกลับจากหมวด -> report (PK ขึ้นต้นด้วย report_id ใช้ไม่ได้)
CREATE INDEX ix_report_categories_category ON report_categories (category_id);                       -- (M-N)
-- call_logs: dashboard
CREATE INDEX ix_call_logs_created           ON call_logs (created_at DESC, id DESC);                 -- IDX-6
CREATE INDEX ix_call_logs_high_risk_created ON call_logs (created_at) WHERE risk_score >= 80;        -- IDX-7 partial
CREATE INDEX ix_call_logs_user_created      ON call_logs (user_id, created_at DESC, id DESC)
  WHERE user_id IS NOT NULL;                                                                         -- IDX-8 partial
-- emergency_contacts
CREATE INDEX ix_emergency_contacts_user ON emergency_contacts (user_id);                             -- IDX-9
VACUUM ANALYZE;
\echo '>>> Indexes ready'
