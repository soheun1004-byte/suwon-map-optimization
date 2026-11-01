"""
데이터 공급 파이프라인: 데이터 파일 → 엔진 입력값(d, τ, U)

1) data/processed/ 에 아래 3개 CSV가 있으면 그걸 읽고 (실데이터)
2) 없으면 예시(난수) 데이터를 만들어서 씀 → 실데이터가 없어도 API·대시보드 개발 가능

[실데이터 CSV 형식] ← 오늘 운행내역에서 만들어야 하는 것
  grids.csv   grid_id, lat, lon                 500m 격자 중심 좌표
  demand.csv  grid_id, slot, calls              격자·시간대별 평균 즉시콜 수 (고객 취소 포함)
  sites.csv   site_id, name, lat, lon, capacity 후보 거점(병원·복지관 주차장, 차고지)

이동시간 τ = 직선거리(km) ÷ 시간대별 속도(SPEED_KMH)
  ※ 지금은 직선거리. 나중에 실제 도로 이동시간으로 바꿀 자리.
"""
import csv
import math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "processed"
SPEED_KMH = {"09-12": 27.0, "15-18": 21.0}   # 시간대별 실효속도 가정 (km/h)


def haversine_km(lat1, lon1, lat2, lon2):
    """위도·경도 두 점 사이 직선거리(km)"""
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(a))


def _read_csv(name):
    with open(DATA_DIR / name, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _sample_dataset():
    """예시 데이터: 수원 시청 근처 10km × 10km 안에 격자 40개, 후보 12곳 (난수, 실제 아님)"""
    rng = np.random.default_rng(2026)
    lat0, lon0 = 37.2636, 127.0286 - 0.056          # 지도 왼쪽 아래 기준점 근처
    km_lat, km_lon = 1 / 111.0, 1 / 88.4            # 1km를 위도·경도로
    to_ll = lambda x, y: (round(lat0 - 0.045 + y * km_lat, 6), round(lon0 + x * km_lon, 6))
    hot = np.array([[3, 7], [7, 3], [6, 8]])
    gxy = np.clip(hot[rng.integers(0, 3, 40)] + rng.normal(0, 1.4, (40, 2)), 0, 10)
    sxy = rng.uniform(0.5, 9.5, (12, 2))
    grids = [dict(grid_id=f"G{i:03d}", lat=to_ll(*gxy[i])[0], lon=to_ll(*gxy[i])[1]) for i in range(40)]
    sites = [dict(site_id=f"S{j:02d}", name=f"예시 거점 {j}", lat=to_ll(*sxy[j])[0],
                  lon=to_ll(*sxy[j])[1], capacity=int(c))
             for j, c in enumerate(rng.integers(70, 120, 12))]
    demand = {"09-12": rng.poisson(6, 40) + 1, "15-18": rng.poisson(4, 40) + 1}
    demand = {s: {g["grid_id"]: float(v) for g, v in zip(grids, vals)} for s, vals in demand.items()}
    return dict(source="sample", grids=grids, sites=sites, demand=demand)


def load_dataset():
    files = ["grids.csv", "demand.csv", "sites.csv"]
    if not all((DATA_DIR / f).exists() for f in files):
        return _sample_dataset()
    grids = [dict(grid_id=r["grid_id"], lat=float(r["lat"]), lon=float(r["lon"]))
             for r in _read_csv("grids.csv")]
    sites = [dict(site_id=r["site_id"], name=r["name"], lat=float(r["lat"]),
                  lon=float(r["lon"]), capacity=int(float(r["capacity"])))
             for r in _read_csv("sites.csv")]
    demand = {}
    for r in _read_csv("demand.csv"):
        demand.setdefault(r["slot"], {})[r["grid_id"]] = float(r["calls"])
    return dict(source="processed", grids=grids, sites=sites, demand=demand)


def build_problem(ds, slot):
    """데이터셋 + 시간대 → 엔진 입력 (d, tau, U). 호출이 0인 격자는 뺌."""
    if slot not in ds["demand"]:
        raise KeyError(slot)
    speed = SPEED_KMH.get(slot, 24.0)
    grids = [g for g in ds["grids"] if ds["demand"][slot].get(g["grid_id"], 0) > 0]
    d = np.array([ds["demand"][slot][g["grid_id"]] for g in grids])
    tau = np.array([[haversine_km(g["lat"], g["lon"], s["lat"], s["lon"]) / speed * 60
                     for s in ds["sites"]] for g in grids])
    U = np.array([s["capacity"] for s in ds["sites"]])
    return d, tau, U, grids
