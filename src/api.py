"""
관제 센터 대시보드용 백엔드 REST API (Flask)

실행:  python src/api.py   →  http://127.0.0.1:5000/api/health

엔드포인트
  GET  /api/health                 서버 살아있는지
  GET  /api/slots                  시간대 목록
  GET  /api/sites                  후보 거점 목록 (좌표, 용량)
  GET  /api/demand?slot=09-12      격자별 호출 수 (지도 히트맵용)
  POST /api/optimize               {"slot": "09-12", "P": 4} → 선정 거점, 배정, 평균 이동시간
  --- 2주차 스키마 연동 (9주차) ---
  POST /api/messages               운전원 앱 → 위치·상태 메시지 (schema.json 형식). 검사 후 vehicle_logs 저장
                                   status가 IDLE(빈 차)이면 응답에 대기 거점 추천이 같이 옴
  GET  /api/vehicles               차량별 최신 위치·상태 (대시보드 지도용)
  GET  /api/recommend?lat=..&lon=..[&slot=09-12&P=4]   현재 위치에서 갈 대기 거점 추천
  --- 수요 분석 및 선제 배치 계획 화면 (10주차) ---
  GET  /api/patterns?slot=09-12[&top=10]    ① 시간대별 이동 패턴 (출발·도착 집중 격자, 주요 경로, 주거지·목적지 추정)
  GET  /api/forecast?slot=09-12[&top=10]    ② 시간대별 수요 전망 (예상 호출 수, 수요 증가 예상 격자, 선제 배치 제안 거점)
  GET  /api/plan?slot=09-12&P=4[&vehicles=20]  ③ 차량 배치 계획 (거점별 배치 대수, 빈 차 이동 지시)
"""
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import solve_pmedian
from pipeline import load_dataset, build_problem, haversine_km, SPEED_KMH
import db
import analysis

app = Flask(__name__)
app.json.ensure_ascii = False          # 한글 그대로 출력
DATA = load_dataset()                  # 서버 켤 때 한 번 읽음
app.config["DB_PATH"] = db.DEFAULT_DB  # 테스트에서는 임시 파일로 바꿔 씀
_plan_cache = {}                       # (slot, P) → 최적화 결과. 같은 요청은 다시 안 풂


@app.after_request
def allow_dashboard(resp):
    """대시보드(다른 주소에서 실행되는 웹페이지)가 이 API를 부를 수 있게 허용 (CORS)"""
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@app.get("/api/health")
def health():
    return jsonify(status="ok", data_source=DATA["source"])


@app.get("/api/slots")
def slots():
    return jsonify(slots=sorted(DATA["demand"].keys()))


@app.get("/api/sites")
def sites():
    return jsonify(data_source=DATA["source"], sites=DATA["sites"])


@app.get("/api/demand")
def demand():
    slot = request.args.get("slot")
    if slot not in DATA["demand"]:
        return jsonify(error=f"slot은 {sorted(DATA['demand'])} 중 하나"), 400
    rows = [dict(g, calls=DATA["demand"][slot].get(g["grid_id"], 0)) for g in DATA["grids"]]
    return jsonify(data_source=DATA["source"], slot=slot, grids=rows)


@app.route("/api/optimize", methods=["POST", "OPTIONS"])
def optimize():
    if request.method == "OPTIONS":
        return "", 204
    body = request.get_json(silent=True) or {}
    slot, P = body.get("slot"), body.get("P", 4)
    if slot not in DATA["demand"]:
        return jsonify(error=f"slot은 {sorted(DATA['demand'])} 중 하나"), 400
    if not isinstance(P, int) or not 1 <= P <= len(DATA["sites"]):
        return jsonify(error=f"P는 1~{len(DATA['sites'])} 사이 정수"), 400

    d, tau, U, grids = build_problem(DATA, slot)
    r = solve_pmedian(d, tau, U, P)
    if r["status"] != "optimal":
        return jsonify(status=r["status"], message=r["message"]), 422

    load = {}
    for i, j, share in r["assign"]:
        load[j] = load.get(j, 0) + d[i] * share
    open_sites = [dict(DATA["sites"][j], load=round(load.get(j, 0), 2)) for j in r["open_sites"]]
    assignments = [dict(grid_id=grids[i]["grid_id"], site_id=DATA["sites"][j]["site_id"], share=share)
                   for i, j, share in r["assign"]]
    return jsonify(status="optimal", data_source=DATA["source"], slot=slot, P=P,
                   avg_travel_min=round(r["avg_min"], 2), solve_sec=round(r["solve_sec"], 3),
                   open_sites=open_sites, assignments=assignments)


# ---------------- 2주차 스키마 연동 ----------------
def current_slot():
    """지금 시각에 맞는 시간대. 정해진 시간대 밖이면 첫 번째 시간대 사용 (임시 규칙)"""
    h = datetime.now().hour
    slots = sorted(DATA["demand"])
    for s in slots:
        a, b = map(int, s.split("-"))
        if a <= h < b:
            return s
    return slots[0]


def plan(slot, P):
    if (slot, P) not in _plan_cache:
        d, tau, U, _ = build_problem(DATA, slot)
        _plan_cache[(slot, P)] = solve_pmedian(d, tau, U, P)
    return _plan_cache[(slot, P)]


def recommend_site(lat, lon, slot, P, vehicle_id=None):
    """그 시간대에 선정된 대기 거점 중, 현재 위치에서 가장 빨리 갈 수 있는 곳"""
    r = plan(slot, P)
    if r["status"] != "optimal":
        return None
    speed = SPEED_KMH.get(slot, 24.0)
    best = min((haversine_km(lat, lon, DATA["sites"][j]["lat"], DATA["sites"][j]["lon"]) / speed * 60, j)
               for j in r["open_sites"])
    site = DATA["sites"][best[1]]
    # 운전원 앱에 그대로 보낼 수 있는 2주차 스키마 형식 메시지
    command = {"header": {"messageId": str(uuid.uuid4()), "senderId": "CONTROL",
                          "receiverId": vehicle_id or "UNKNOWN",
                          "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")},
               "payload": {"vehicleId": vehicle_id or "UNKNOWN", "status": "IDLE",
                           "latitude": site["lat"], "longitude": site["lon"],
                           "targetSiteId": site["site_id"]}}
    return dict(slot=slot, P=P, site=site, travel_min=round(best[0], 1), command=command)


@app.route("/api/messages", methods=["POST", "OPTIONS"])
def receive_message():
    if request.method == "OPTIONS":
        return "", 204
    msg = request.get_json(silent=True)
    if msg is None:
        return jsonify(error="JSON 본문이 필요함"), 400
    errors = db.validate_message(msg)
    if errors:
        return jsonify(error="schema.json 형식 오류", details=errors), 400
    con = db.connect(app.config["DB_PATH"])
    log_id = db.save_message(con, msg); con.close()
    out = dict(saved=True, log_id=log_id)
    p = msg["payload"]
    if p["status"] == "IDLE" and "latitude" in p and "longitude" in p:
        out["recommendation"] = recommend_site(p["latitude"], p["longitude"], current_slot(), 4, p["vehicleId"])
    return jsonify(out), 201


@app.get("/api/vehicles")
def vehicles():
    con = db.connect(app.config["DB_PATH"])
    rows = db.latest_vehicles(con); con.close()
    return jsonify(vehicles=rows)


@app.get("/api/recommend")
def recommend():
    try:
        lat, lon = float(request.args["lat"]), float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify(error="lat, lon 숫자가 필요함"), 400
    slot = request.args.get("slot") or current_slot()
    P = int(request.args.get("P", 4))
    if slot not in DATA["demand"] or not 1 <= P <= len(DATA["sites"]):
        return jsonify(error="slot 또는 P가 잘못됨"), 400
    rec = recommend_site(lat, lon, slot, P, request.args.get("vehicleId"))
    if rec is None:
        return jsonify(error="해를 찾지 못함"), 422
    return jsonify(rec)


# ---------------- 수요 분석 및 선제 배치 계획 화면 (10주차) ----------------
def _slot_arg():
    slot = request.args.get("slot")
    return slot if slot in DATA["demand"] else None


def _int_arg(name, default, lo, hi):
    try:
        v = int(request.args.get(name, default))
    except ValueError:
        return None
    return v if lo <= v <= hi else None


@app.get("/api/patterns")
def patterns():
    slot, top = request.args.get("slot"), _int_arg("top", 10, 1, 100)
    if slot not in (DATA.get("od") or {}):
        return jsonify(error=f"이동 패턴 데이터(od.csv)가 있는 시간대: {sorted(DATA.get('od') or {})}"), 400
    if top is None:
        return jsonify(error="top은 1~100"), 400
    return jsonify(dict(analysis.movement_patterns(DATA, slot, top), data_source=DATA["source"]))


@app.get("/api/forecast")
def forecast():
    slot, top = _slot_arg(), _int_arg("top", 10, 1, 100)
    P = _int_arg("P", 4, 1, len(DATA["sites"]))
    if slot is None or top is None or P is None:
        return jsonify(error=f"slot은 {sorted(DATA['demand'])} 중 하나, top 1~100, P 1~{len(DATA['sites'])}"), 400
    out = analysis.demand_outlook(DATA, slot, top)
    r = plan(slot, P)                                     # 선제 배치 제안 = 이 시간대 p-median 선정 거점
    out["suggested_sites"] = ([DATA["sites"][j] for j in r["open_sites"]] if r["status"] == "optimal" else [])
    out["data_source"] = DATA["source"]
    return jsonify(out)


@app.get("/api/plan")
def deployment():
    slot = _slot_arg() or (current_slot() if "slot" not in request.args else None)
    P = _int_arg("P", 4, 1, len(DATA["sites"]))
    n = _int_arg("vehicles", 0, 0, 500)
    if slot is None or P is None or n is None:
        return jsonify(error="slot, P(1~후보 수), vehicles(0~500)를 확인"), 400
    con = db.connect(app.config["DB_PATH"])
    idle = [dict(vehicle_id=v["vehicle_id"], latitude=float(v["latitude"]), longitude=float(v["longitude"]))
            for v in db.latest_vehicles(con)
            if v["status"] == "IDLE" and v["latitude"] is not None and v["longitude"] is not None]
    con.close()
    # 실제 빈 차가 있으면 그 차들로, 없으면 vehicles 대수로 계획
    out = analysis.deployment_plan(DATA, slot, P, idle_vehicles=idle or None, n_vehicles=n)
    if out["status"] != "optimal":
        return jsonify(out), 422
    out["vehicle_source"] = "vehicle_logs(IDLE)" if idle else "vehicles 파라미터"
    out["data_source"] = DATA["source"]
    return jsonify(out)


if __name__ == "__main__":
    print(f"데이터: {DATA['source']}  (processed=실데이터, sample=예시)")
    app.run(host="127.0.0.1", port=5000, debug=True)
