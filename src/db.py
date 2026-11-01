"""
2주차 스키마 연동: 운전원 앱 메시지 검사(schema.json) + 저장(vehicle_logs 테이블)

- 검사: schema/schema.json (2주차 JSON 스키마, 9주차에 IDLE·targetSiteId 추가)
- 저장: 지금은 SQLite(schema/schema_sqlite.sql) — 설치 없이 동작
        실서버에서는 같은 테이블을 PostgreSQL(schema/schema.sql)로 옮기면 됨
- DB 파일 위치: data/processed/app.db (.gitignore로 GitHub에 안 올라감)
"""
import json
import sqlite3
from pathlib import Path
from jsonschema import Draft7Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schema" / "schema.json").read_text(encoding="utf-8"))
DDL = (ROOT / "schema" / "schema_sqlite.sql").read_text(encoding="utf-8")
DEFAULT_DB = ROOT / "data" / "processed" / "app.db"
_validator = Draft7Validator(SCHEMA, format_checker=FormatChecker())


def validate_message(msg):
    """형식 오류 목록을 돌려줌. 빈 리스트면 통과."""
    return [f"{'/'.join(map(str, e.path)) or '(전체)'}: {e.message}"
            for e in sorted(_validator.iter_errors(msg), key=lambda e: list(e.path))]


def connect(db_path=DEFAULT_DB):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.executescript(DDL)
    return con


def save_message(con, msg):
    """검사를 통과한 메시지를 vehicle_logs에 한 줄로 저장 (원본은 raw_payload에 통째로)"""
    h, p = msg["header"], msg["payload"]
    cur = con.execute(
        "INSERT INTO vehicle_logs (message_id, vehicle_id, status, latitude, longitude, raw_payload, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (h["messageId"], p["vehicleId"], p["status"], p.get("latitude"), p.get("longitude"),
         json.dumps(msg, ensure_ascii=False), h["timestamp"]))
    con.commit()
    return cur.lastrowid


def latest_vehicles(con):
    """차량별 가장 최근 상태 1줄씩 (대시보드 지도용)"""
    rows = con.execute("""
        SELECT vehicle_id, status, latitude, longitude, created_at FROM vehicle_logs v
        WHERE log_id = (SELECT MAX(log_id) FROM vehicle_logs WHERE vehicle_id = v.vehicle_id)
        ORDER BY vehicle_id""").fetchall()
    return [dict(r) for r in rows]
