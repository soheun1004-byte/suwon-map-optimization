"""10주차: 수요 분석 및 선제 배치 계획 화면용 계산·API 테스트

손으로 결과를 알 수 있는 작은 데이터로 계산 규칙을 확인한다.
"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import analysis
from api import app

# 격자 4개 (H=주거지, D=목적지, X·Y=기타). 좌표는 수원 근처 아무 점
GRIDS = [dict(grid_id="H", lat=37.27, lon=127.00), dict(grid_id="D", lat=37.28, lon=127.03),
         dict(grid_id="X", lat=37.26, lon=127.02), dict(grid_id="Y", lat=37.29, lon=127.01)]
DS = dict(
    grids=GRIDS,
    sites=[dict(site_id="S1", name="거점1", lat=37.27, lon=127.00, capacity=100),
           dict(site_id="S2", name="거점2", lat=37.28, lon=127.03, capacity=100)],
    demand={"09-12": {"H": 8, "D": 2, "X": 1, "Y": 1}, "15-18": {"H": 2, "D": 6, "X": 1, "Y": 1}},
    od={"09-12": {("H", "D"): 6, ("X", "Y"): 1},       # 오전: H에서 나가 D로 감
        "15-18": {("D", "H"): 5, ("Y", "X"): 1}},      # 오후: D에서 나와 H로 돌아옴
)


# ---------- ① 이동 패턴 ----------
def test_top_origin_and_flow():
    r = analysis.movement_patterns(DS, "09-12")
    assert r["top_origins"][0]["grid_id"] == "H"
    assert r["top_destinations"][0]["grid_id"] == "D"
    assert (r["top_flows"][0]["origin"], r["top_flows"][0]["dest"]) == ("H", "D")
    assert r["total_trips"] == 7


def test_home_and_destination_estimate():
    p = analysis.estimate_places(DS)
    assert p["homes"][0]["grid_id"] == "H"           # 오전 출발 + 오후 도착
    assert p["destinations"][0]["grid_id"] == "D"    # 오전 도착 + 오후 출발


# ---------- ② 수요 전망 ----------
def test_rising_grid():
    r = analysis.demand_outlook(DS, "09-12")
    rows = {g["grid_id"]: g for g in r["grids"]}
    assert rows["H"]["usual_calls"] == 5             # (8 + 2) / 2
    assert rows["H"]["ratio"] == 1.6 and rows["H"]["rising"]
    assert not rows["D"]["rising"]                   # 2 / 4 = 0.5
    assert [g["grid_id"] for g in r["rising_grids"]] == ["H"]


def test_rising_flips_in_afternoon():
    r = analysis.demand_outlook(DS, "15-18")
    assert [g["grid_id"] for g in r["rising_grids"]] == ["D"]


# ---------- ③ 배치 계획 ----------
def test_split_vehicles_by_load():
    assert analysis._largest_remainder([3, 1], 4) == [3, 1]
    assert sum(analysis._largest_remainder([1, 1, 1], 10)) == 10


def test_plan_counts_follow_demand():
    r = analysis.deployment_plan(DS, "09-12", P=2, n_vehicles=6)
    v = {s["site_id"]: s["vehicles"] for s in r["sites"]}
    assert sum(v.values()) == 6
    assert v["S1"] > v["S2"]                         # 오전엔 H(거점1 근처) 수요가 많음


def test_plan_moves_nearest_idle_cars():
    idle = [dict(vehicle_id="V1", latitude=37.2701, longitude=127.0001),
            dict(vehicle_id="V2", latitude=37.2799, longitude=127.0299)]
    r = analysis.deployment_plan(DS, "15-18", P=2, idle_vehicles=idle)
    m = {x["vehicle_id"]: x["target_site_id"] for x in r["moves"]}
    assert len(m) == 2 and set(m.values()) <= {"S1", "S2"}
    assert m["V2"] == "S2"                          # 이미 거점2 옆에 있는 차는 거점2로


# ---------- API (예시 데이터) ----------
@pytest.fixture
def client(tmp_path):
    app.config["DB_PATH"] = tmp_path / "t.db"
    return app.test_client()


def test_api_patterns(client):
    b = client.get("/api/patterns?slot=09-12").get_json()
    assert b["top_flows"] and b["places"]["homes"]
    assert client.get("/api/patterns?slot=00-01").status_code == 400


def test_api_forecast(client):
    b = client.get("/api/forecast?slot=15-18&P=4").get_json()
    assert len(b["suggested_sites"]) == 4 and "rising_grids" in b


def test_api_plan_with_count_and_with_idle(client):
    b = client.get("/api/plan?slot=09-12&P=4&vehicles=20").get_json()
    assert b["n_vehicles"] == 20 and sum(s["vehicles"] for s in b["sites"]) == 20
    msg = {"header": {"messageId": "m1", "senderId": "V9", "receiverId": "CONTROL",
                      "timestamp": "2026-11-06T16:00:00+09:00"},
           "payload": {"vehicleId": "V9", "status": "IDLE", "latitude": 37.25, "longitude": 127.0}}
    client.post("/api/messages", json=msg)
    b = client.get("/api/plan?slot=09-12&P=4").get_json()
    assert b["vehicle_source"] == "vehicle_logs(IDLE)" and b["moves"][0]["vehicle_id"] == "V9"
    assert client.get("/api/plan?slot=bad").status_code == 400
