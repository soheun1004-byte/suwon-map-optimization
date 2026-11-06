"""
관제 대시보드 '수요 분석 및 선제 배치 계획' 화면용 계산 (10주차)

화면의 3개 영역과 1:1로 대응한다.
  ① movement_patterns  시간대별 이동 패턴: 출발·도착이 몰리는 격자, 주요 이동 경로,
                        반복 패턴으로 본 주거지·주요 목적지 추정
  ② demand_outlook     시간대별 수요 전망: 그 시간대 예상 호출 수, 평소보다 수요가 늘어나는 격자
  ③ deployment_plan    차량 배치 계획: 대기 거점별 배치 대수, 빈 차별 이동 지시

※ ②의 '예상 호출 수'는 과거 같은 시간대 평균값이다 (v0.1).
   머신러닝 예측 모델이 아니므로 보고서·발표에서는 '과거 운행 데이터 기반 수요 추정'이라고 쓴다.
"""
import numpy as np

from engine import solve_pmedian
from pipeline import build_problem, haversine_km, SPEED_KMH


def _grid_index(ds):
    return {g["grid_id"]: g for g in ds["grids"]}


def _top(counter, n):
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


# ---------------------------------------------------------------- ①
def movement_patterns(ds, slot, top=10):
    """
    od[slot] = {(출발 격자, 도착 격자): 하루 평균 통행 수}
    - 출발이 많은 격자 / 도착이 많은 격자 / 통행이 많은 경로(출발→도착)
    - 주거지·주요 목적지 추정 (전체 시간대 사용)
        주거지 후보   : 오전에 '출발'이 많고, 오후에 '도착'이 많은 격자 (나갔다가 돌아오는 곳)
        주요 목적지   : 오전에 '도착'이 많고, 오후에 '출발'이 많은 격자 (갔다가 떠나는 곳)
    """
    od_all = ds.get("od") or {}
    if slot not in od_all:
        raise KeyError(slot)
    G = _grid_index(ds)
    od = od_all[slot]

    out_cnt, in_cnt = {}, {}
    for (o, d), n in od.items():
        out_cnt[o] = out_cnt.get(o, 0) + n
        in_cnt[d] = in_cnt.get(d, 0) + n
    total = sum(od.values()) or 1

    def cell(gid, n):
        g = G.get(gid, {})
        return dict(grid_id=gid, lat=g.get("lat"), lon=g.get("lon"), trips=round(n, 2),
                    share=round(n / total, 4))

    flows = []
    for (o, d), n in _top(od, top):
        go, gd = G.get(o, {}), G.get(d, {})
        km = (haversine_km(go["lat"], go["lon"], gd["lat"], gd["lon"])
              if go and gd else None)
        flows.append(dict(origin=o, dest=d, trips=round(n, 2),
                          origin_lat=go.get("lat"), origin_lon=go.get("lon"),
                          dest_lat=gd.get("lat"), dest_lon=gd.get("lon"),
                          km=round(km, 2) if km is not None else None))

    return dict(slot=slot, total_trips=round(total, 2),
                top_origins=[cell(g, n) for g, n in _top(out_cnt, top)],
                top_destinations=[cell(g, n) for g, n in _top(in_cnt, top)],
                top_flows=flows,
                places=estimate_places(ds, top))


def estimate_places(ds, top=10):
    """12시 전 시간대 중 통행이 가장 많은 때를 '오전', 12시 이후 중 가장 많은 때를 '오후'로 보고
    반복 이동 패턴(나갔다가 돌아오는지)으로 격자 성격을 추정"""
    od_all = ds.get("od") or {}
    vol = {s: sum(v.values()) for s, v in od_all.items()}
    am_s = [s for s in vol if int(s.split("-")[0]) < 12]
    pm_s = [s for s in vol if int(s.split("-")[0]) >= 12]
    if not am_s or not pm_s:
        return dict(note="오전·오후 시간대 이동 데이터가 모두 있어야 추정 가능", homes=[], destinations=[])
    am, pm = max(am_s, key=vol.get), max(pm_s, key=vol.get)

    def side(slot, idx):
        c = {}
        for k, n in od_all[slot].items():
            c[k[idx]] = c.get(k[idx], 0) + n
        tot = sum(c.values()) or 1
        return {g: v / tot for g, v in c.items()}            # 비율로 맞춰서 시간대 규모 차이 제거

    am_out, am_in, pm_out, pm_in = side(am, 0), side(am, 1), side(pm, 0), side(pm, 1)
    grids = set(am_out) | set(am_in) | set(pm_out) | set(pm_in)
    home = {g: am_out.get(g, 0) + pm_in.get(g, 0) - am_in.get(g, 0) - pm_out.get(g, 0) for g in grids}
    G = _grid_index(ds)

    def pack(items):
        return [dict(grid_id=g, lat=G.get(g, {}).get("lat"), lon=G.get(g, {}).get("lon"),
                     score=round(s, 4)) for g, s in items]

    homes = [(g, s) for g, s in _top(home, top) if s > 0]
    dests = [(g, -s) for g, s in sorted(home.items(), key=lambda kv: (kv[1], kv[0]))[:top] if s < 0]
    return dict(morning_slot=am, afternoon_slot=pm,
                rule="주거지 점수 = 오전 출발 비율 + 오후 도착 비율 − 오전 도착 비율 − 오후 출발 비율",
                homes=pack(homes), destinations=pack(dests))


# ---------------------------------------------------------------- ②
def demand_outlook(ds, slot, top=10, rise_ratio=1.2, min_calls=1.0):
    """
    예상 호출 수 = 과거 같은 시간대 평균 (demand[slot])
    평소 수준   = 그 격자의 전체 시간대 평균
    증가 배율   = 예상 호출 수 ÷ 평소 수준 → rise_ratio 이상이고 min_calls 이상이면 '수요 증가 예상'
    """
    if slot not in ds["demand"]:
        raise KeyError(slot)
    slots = sorted(ds["demand"])
    rows = []
    for g in ds["grids"]:
        gid = g["grid_id"]
        exp = ds["demand"][slot].get(gid, 0.0)
        usual = float(np.mean([ds["demand"][s].get(gid, 0.0) for s in slots]))
        ratio = exp / usual if usual > 0 else 0.0
        rows.append(dict(grid_id=gid, lat=g["lat"], lon=g["lon"], expected_calls=round(exp, 2),
                         usual_calls=round(usual, 2), ratio=round(ratio, 2),
                         rising=bool(ratio >= rise_ratio and exp >= min_calls)))
    rising = sorted([r for r in rows if r["rising"]], key=lambda r: (-r["expected_calls"], r["grid_id"]))
    total = sum(r["expected_calls"] for r in rows) or 1
    top_rows = sorted(rows, key=lambda r: (-r["expected_calls"], r["grid_id"]))[:top]
    return dict(slot=slot, method="과거 동일 시간대 평균 (v0.1)",
                total_expected_calls=round(total, 2),
                top_share=round(sum(r["expected_calls"] for r in top_rows) / total, 4),
                grids=rows, top_grids=top_rows, rising_grids=rising[:top])


# ---------------------------------------------------------------- ③
def _largest_remainder(weights, total):
    """비율대로 정수 total을 나눔 (합이 정확히 total)"""
    w = np.asarray(weights, dtype=float)
    if total <= 0 or w.sum() <= 0:
        return [0] * len(w)
    raw = w / w.sum() * total
    base = np.floor(raw).astype(int)
    for k in np.argsort(-(raw - base))[: total - base.sum()]:
        base[k] += 1
    return base.tolist()


def deployment_plan(ds, slot, P, idle_vehicles=None, n_vehicles=None):
    """
    1) p-median으로 이 시간대 대기 거점 P곳 선정 (엔진 그대로 사용)
    2) 거점이 맡는 호출 수(load) 비율대로 빈 차 대수를 나눔
    3) 실제 빈 차 위치가 있으면, 가까운 차부터 자리가 남은 거점에 배정 (이동 지시 목록)
    idle_vehicles: [{"vehicle_id", "latitude", "longitude"}]  (/api/vehicles 중 IDLE)
    n_vehicles   : 빈 차 위치 없이 대수만 정해 볼 때
    """
    d, tau, U, grids = build_problem(ds, slot)
    r = solve_pmedian(d, tau, U, P)
    if r["status"] != "optimal":
        return dict(status=r["status"], message=r["message"])

    load, cover = {}, {}
    for i, j, share in r["assign"]:
        load[j] = load.get(j, 0) + d[i] * share
        cover.setdefault(j, []).append((grids[i]["grid_id"], d[i] * share))

    idle = list(idle_vehicles or [])
    n = len(idle) if idle else int(n_vehicles or 0)
    opened = r["open_sites"]
    quota = _largest_remainder([load.get(j, 0) for j in opened], n)

    sites = []
    for j, q in zip(opened, quota):
        s = ds["sites"][j]
        top_cover = sorted(cover.get(j, []), key=lambda x: -x[1])[:3]
        sites.append(dict(s, load=round(load.get(j, 0), 2), vehicles=q,
                          covers=[g for g, _ in top_cover],
                          reason=f"예상 호출 {load.get(j, 0):.1f}건을 맡음 "
                                 f"(주요 격자: {', '.join(g for g, _ in top_cover)})"))

    moves = []
    if idle:
        speed = SPEED_KMH.get(slot, 24.0)
        left = {s["site_id"]: s["vehicles"] for s in sites}
        pairs = sorted((haversine_km(v["latitude"], v["longitude"], s["lat"], s["lon"]) / speed * 60,
                        v["vehicle_id"], s["site_id"]) for v in idle for s in sites)
        done = set()
        for t, vid, sid in pairs:                      # 가까운 쌍부터 확정 (탐욕적 배정)
            if vid in done or left[sid] <= 0:
                continue
            moves.append(dict(vehicle_id=vid, target_site_id=sid, travel_min=round(t, 1)))
            done.add(vid); left[sid] -= 1
        moves.sort(key=lambda m: m["vehicle_id"])

    return dict(status="optimal", slot=slot, P=P, n_vehicles=n,
                avg_travel_min=round(r["avg_min"], 2), solve_sec=round(r["solve_sec"], 3),
                sites=sites, moves=moves)
