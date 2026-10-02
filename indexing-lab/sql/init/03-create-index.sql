-- สร้าง index หลัง seed (เฉพาะ pg_with_index)
\echo '>>> Creating indexes ...'
CREATE INDEX idx_tx_date     ON transactions (transaction_date);
CREATE INDEX idx_tx_customer ON transactions (customer_id);
ANALYZE transactions;
\echo '>>> Indexes ready'
