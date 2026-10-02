-- ตารางธุรกรรม (ใช้ทั้ง 2 database)
CREATE TABLE transactions (
  id               BIGSERIAL PRIMARY KEY,
  transaction_date DATE           NOT NULL,
  customer_id      INT            NOT NULL,
  amount           NUMERIC(10, 2) NOT NULL,
  status           VARCHAR(10)    NOT NULL,
  description      VARCHAR(255)
);
