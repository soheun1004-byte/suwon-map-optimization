"""
관제 센터 대시보드용 백엔드 REST API (Flask)

실행:  python src/api.py   →  http://127.0.0.1:5000/api/health

엔드포인트
  GET  /api/health                 서버 살아있는지
  GET  /api/slots                  시간대 목록
  GET  /api/sites                  후보 거점 목록 (좌표, 용량)
  GET  /api/demand?slot=09-12      격자별 호출 수 (지도 히트맵용)
  POST /api/optimize               {"slot": "09-12", "P": 4} → 선정 거점, 배정, 평균 이동시간
"""
import sys
from pathlib import Path
from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import solve_pmedian
from pipeline import load_dataset, build_problem

app = Flask(__name__)
app.json.ensure_ascii = False          # 한글 그대로 출력
DATA = load_dataset()                  # 서버 켤 때 한 번 읽음


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


if __name__ == "__main__":
    print(f"데이터: {DATA['source']}  (processed=실데이터, sample=예시)")
    app.run(host="127.0.0.1", port=5000, debug=True)
