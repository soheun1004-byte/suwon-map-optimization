"""API 테스트: 서버를 실제로 켜지 않고 요청을 흉내 내서 응답 형식을 확인"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from api import app

client = app.test_client()


def test_health():
    assert client.get("/api/health").get_json()["status"] == "ok"


def test_demand_and_sites():
    g = client.get("/api/demand?slot=09-12").get_json()["grids"]
    assert {"grid_id", "lat", "lon", "calls"} <= set(g[0])
    s = client.get("/api/sites").get_json()["sites"]
    assert {"site_id", "name", "lat", "lon", "capacity"} <= set(s[0])


def test_optimize():
    r = client.post("/api/optimize", json={"slot": "09-12", "P": 4})
    body = r.get_json()
    assert r.status_code == 200 and body["status"] == "optimal"
    assert len(body["open_sites"]) == 4
    assert body["avg_travel_min"] > 0


def test_optimize_bad_input():
    assert client.post("/api/optimize", json={"slot": "아무거나"}).status_code == 400
    assert client.post("/api/optimize", json={"slot": "09-12", "P": 99}).status_code == 400
