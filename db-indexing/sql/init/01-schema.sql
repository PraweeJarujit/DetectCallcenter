-- =====================================================================
-- Schema จริงของ DetectCallcenter (สร้างจาก Alembic migration 0001)
--   alembic upgrade 0001 --sql
-- มีแค่ PK / UNIQUE / FK (เหมือนตอนยังไม่ทำ index) — ใช้ทั้ง 2 database
-- =====================================================================

CREATE TABLE users (
    id UUID NOT NULL, 
    username VARCHAR(50) NOT NULL, 
    email VARCHAR(255) NOT NULL, 
    hashed_password VARCHAR(255) NOT NULL, 
    full_name VARCHAR(150), 
    role VARCHAR(10) NOT NULL, 
    is_active BOOLEAN NOT NULL, 
    auto_notify BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (email), 
    UNIQUE (username)
);

CREATE TABLE token_blacklist (
    id UUID NOT NULL, 
    jti VARCHAR(64) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE, 
    revoked_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (jti)
);

CREATE TABLE blacklist_numbers (
    id UUID NOT NULL, 
    phone_number VARCHAR(20) NOT NULL, 
    status VARCHAR(10) NOT NULL, 
    risk_score INTEGER NOT NULL, 
    report_count INTEGER NOT NULL, 
    first_reported_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    last_reported_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX uq_blacklist_numbers_phone ON blacklist_numbers (phone_number varchar_pattern_ops);

CREATE TABLE scam_categories (
    id SERIAL NOT NULL, 
    code VARCHAR(40) NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (code)
);

CREATE TABLE call_logs (
    id BIGSERIAL NOT NULL, 
    phone_number VARCHAR(20) NOT NULL, 
    user_id UUID, 
    risk_score INTEGER NOT NULL, 
    status VARCHAR(10) NOT NULL, 
    is_synthetic_voice BOOLEAN NOT NULL, 
    source VARCHAR(15) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE TABLE emergency_contacts (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    phone_number VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE reports (
    id UUID NOT NULL, 
    blacklist_number_id UUID NOT NULL, 
    reported_by UUID, 
    risk_score INTEGER NOT NULL, 
    note TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(blacklist_number_id) REFERENCES blacklist_numbers (id) ON DELETE CASCADE, 
    FOREIGN KEY(reported_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE TABLE report_categories (
    report_id UUID NOT NULL, 
    category_id INTEGER NOT NULL, 
    PRIMARY KEY (report_id, category_id), 
    FOREIGN KEY(category_id) REFERENCES scam_categories (id) ON DELETE CASCADE, 
    FOREIGN KEY(report_id) REFERENCES reports (id) ON DELETE CASCADE
);

INSERT INTO scam_categories (code, name) VALUES ('impersonate_police', 'แอบอ้างเป็นตำรวจ/DSI');

INSERT INTO scam_categories (code, name) VALUES ('impersonate_bank', 'แอบอ้างเป็นเจ้าหน้าที่ธนาคาร');

INSERT INTO scam_categories (code, name) VALUES ('parcel', 'พัสดุผิดกฎหมาย/ค้างส่ง');

INSERT INTO scam_categories (code, name) VALUES ('investment', 'ชวนลงทุนผลตอบแทนสูง');

INSERT INTO scam_categories (code, name) VALUES ('loan', 'เงินกู้ออนไลน์');

INSERT INTO scam_categories (code, name) VALUES ('refund', 'คืนเงิน/ภาษี/ค่าไฟ');

INSERT INTO scam_categories (code, name) VALUES ('voice_clone', 'ใช้เสียงสังเคราะห์เลียนแบบคนรู้จัก');

INSERT INTO scam_categories (code, name) VALUES ('other', 'อื่น ๆ');

