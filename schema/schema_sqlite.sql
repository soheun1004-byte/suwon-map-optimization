-- schema.sql(PostgreSQL)과 같은 테이블의 SQLite 버전 — 설치 없이 개발·테스트용
-- 차이: BIGSERIAL → INTEGER AUTOINCREMENT, JSONB → TEXT(JSON 문자열), GIN 인덱스 없음
CREATE TABLE IF NOT EXISTS vehicle_logs (
    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  VARCHAR(64) NOT NULL,
    vehicle_id  VARCHAR(50) NOT NULL,
    status      VARCHAR(20) NOT NULL,
    latitude    DECIMAL(10, 7),
    longitude   DECIMAL(11, 7),
    raw_payload TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_vehicle_logs_vehicle_id ON vehicle_logs(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_logs_created_at ON vehicle_logs(created_at);
