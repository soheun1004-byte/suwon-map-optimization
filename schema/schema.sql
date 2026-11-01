-- PostgreSQL 전용 데이터베이스 스키마 정의
-- 수원시 교통약자 관제-운전원 시스템 DB 인프라

-- 1. 운행 이력 및 수신 데이터 저장 테이블 (JSONB 활용)
CREATE TABLE IF NOT EXISTS vehicle_logs (
    log_id BIGSERIAL PRIMARY KEY,                -- 로그 고유 ID
    message_id VARCHAR(64) NOT NULL,             -- 메시지 식별자
    vehicle_id VARCHAR(50) NOT NULL,             -- 차량 ID
    status VARCHAR(20) NOT NULL,                 -- 차량 상태 (READY, RUNNING 등)
    latitude DECIMAL(10, 7),                     -- 위도
    longitude DECIMAL(11, 7),                    -- 경도
    raw_payload JSONB NOT NULL,                  -- 1주차 JSON 스키마 데이터 원본 통째로 저장
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP -- 수신 일시
);

-- 2. 고속 쿼리를 위한 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_vehicle_logs_vehicle_id ON vehicle_logs(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_logs_created_at ON vehicle_logs(created_at);
-- JSONB 내 필드 검색용 GIN 인덱스
CREATE INDEX IF NOT EXISTS idx_vehicle_logs_payload ON vehicle_logs USING GIN (raw_payload);