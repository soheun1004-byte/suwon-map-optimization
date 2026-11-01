"""2주차 스키마 연동 테스트: 메시지 검사 → 저장 → 차량 조회 → 대기 거점 추천"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import db
from api import app


def make_msg(vehicle="V001", status="RUNNING", lat=37.2636, lon=127.0286, ts="2026-11-01T16:30:00+09:00"):
    return {"header": {"messageId": f"m-{vehicle}-{ts}", "senderId": vehicle, "receiverId": "CONTROL", "timestamp": ts},
            "payload": {"vehicleId": vehicle, "status": status, "latitude": lat, "longitude": lon, "speed": 30}}


@pytest.fixture
def client(tmp_path):
    app.config["DB_PATH"] = tmp_path / "test.db"     # 테스트마다 빈 DB
    return app.test_client()


# ---- 스키마 검사 ----
def test_valid_message_passes():
    assert db.validate_message(make_msg()) == []


def test_missing_header_field_fails():
    m = make_msg(); del m["header"]["timestamp"]
    assert any("timestamp" in e for e in db.validate_message(m))


def test_unknown_status_fails():
    assert db.validate_message(make_msg(status="SLEEPING")) != []


def test_new_IDLE_status_allowed():
    assert db.validate_message(make_msg(status="IDLE")) == []


# ---- API ----
def test_bad_message_rejected(client):
    r = client.post("/api/messages", json={"payload": {"vehicleId": "V1"}})
    assert r.status_code == 400 and "details" in r.get_json()


def test_message_saved_and_latest_vehicle(client):
    client.post("/api/messages", json=make_msg("V001", "RUNNING", ts="2026-11-01T16:00:00+09:00"))
    client.post("/api/messages", json=make_msg("V001", "STOPPED", ts="2026-11-01T16:05:00+09:00"))
    client.post("/api/messages", json=make_msg("V002", "READY"))
    v = {x["vehicle_id"]: x for x in client.get("/api/vehicles").get_json()["vehicles"]}
    assert set(v) == {"V001", "V002"}
    assert v["V001"]["status"] == "STOPPED"          # 가장 최근 상태


def test_IDLE_message_returns_recommendation(client):
    r = client.post("/api/messages", json=make_msg("V003", "IDLE"))
    body = r.get_json()
    assert r.status_code == 201
    rec = body["recommendation"]
    assert rec["site"]["site_id"].startswith("S")
    cmd = rec["command"]                              # 운전원에게 보낼 지시도 2주차 형식이어야 함
    assert db.validate_message(cmd) == []
    assert cmd["payload"]["targetSiteId"] == rec["site"]["site_id"]


def test_recommend_picks_an_open_site(client):
    opened = {s["site_id"] for s in client.post("/api/optimize", json={"slot": "09-12", "P": 4}).get_json()["open_sites"]}
    rec = client.get("/api/recommend?lat=37.25&lon=127.01&slot=09-12&P=4").get_json()
    assert rec["site"]["site_id"] in opened


def test_recommend_bad_input(client):
    assert client.get("/api/recommend?lat=abc").status_code == 400
