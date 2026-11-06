"""
운행내역 원본 → API가 읽는 CSV 4개 만들기 (10주차)

실행 (프로젝트 폴더에서):
    python tools/build_csvs.py 운행내역.xlsx
    python tools/build_csvs.py 운행내역.xlsx --sites 후보거점.csv          # 병원·복지관 주차장 목록이 있을 때
    python tools/build_csvs.py 운행내역.xlsx --grid-centers qgis_grid.csv  # QGIS 격자를 그대로 쓸 때

만들어지는 파일 (data/processed/, GitHub에는 안 올라감)
    grids.csv   grid_id, lat, lon                    500m 격자 중심
    demand.csv  grid_id, slot, calls                 격자·시간대별 '하루 평균' 즉시콜 수 (고객 취소 포함)
    od.csv      slot, origin_grid, dest_grid, trips  시간대별 출발→도착 하루 평균 통행 수 (운행 완료 건)
    sites.csv   site_id, name, lat, lon, capacity    후보 거점 (--sites가 없으면 '하차가 많은 격자'로 임시 생성)

정제 기준은 docs/mapping_rules.md를 따른다.
  - 즉시콜만 (예약콜 제외)   - 평일만 (--all-days로 주말 포함)
  - 승차일시 < 접수일시인 기입 오류 제외   - 좌표 없는 건 제외
"""
import argparse
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed"

# ▼ 원본 엑셀의 열 이름이 다르면 여기만 고치면 됨 (실행하면 원본 열 목록을 먼저 보여줌)
COL = {
    "접수": "접수일시",
    "승차": "승차일시",
    "출발X": "출발지X좌표", "출발Y": "출발지Y좌표",
    "도착X": "목적지X좌표", "도착Y": "목적지Y좌표",
    "예약": "예약콜",          # 예약콜 여부 열
    "결과": "결과",            # 하차 / 고객취소 / ...
}
RESERVED_VALUES = {"Y", "y", "예", "예약", "예약콜", "1", "TRUE", "True"}
DONE_VALUE = "하차"                     # 결과 열에서 '운행 완료'를 뜻하는 값
SLOTS = [(6, 9), (9, 12), (12, 15), (15, 18), (18, 21)]   # 3시간 단위 시간대
CELL_M = 500                                            # 격자 크기(m)
LAT0, LON0 = 37.28, 127.01                              # 수원 근처 기준점 (거리 환산용)


def slot_of(hour):
    for a, b in SLOTS:
        if a <= hour < b:
            return f"{a:02d}-{b:02d}"
    return None


def to_lonlat(x, y):
    """좌표가 경도·위도면 그대로, 미터 단위(TM 좌표)면 pyproj로 변환"""
    if x.between(120, 135).all() and y.between(30, 45).all():
        return x, y
    try:
        from pyproj import Transformer
    except ImportError:
        sys.exit("좌표가 경도·위도가 아니라 미터 단위로 보여요. `pip install pyproj` 후 다시 실행하고,\n"
                 "좌표계가 EPSG:5186이 아니면 아래 EPSG 번호를 바꿔 주세요.")
    t = Transformer.from_crs("EPSG:5186", "EPSG:4326", always_xy=True)
    lon, lat = t.transform(x.values, y.values)
    return pd.Series(lon, index=x.index), pd.Series(lat, index=y.index)


def meters(lon, lat):
    kx = 111_320 * math.cos(math.radians(LAT0))
    return (lon - LON0) * kx, (lat - LAT0) * 110_540


def auto_grid(lon, lat):
    """500m 정사각 격자 번호 G{열}_{행}과 격자 중심 좌표"""
    mx, my = meters(lon, lat)
    gx, gy = (mx // CELL_M).astype(int), (my // CELL_M).astype(int)
    gid = "G" + gx.astype(str) + "_" + gy.astype(str)
    kx = 111_320 * math.cos(math.radians(LAT0))
    clon = LON0 + (gx + 0.5) * CELL_M / kx
    clat = LAT0 + (gy + 0.5) * CELL_M / 110_540
    return gid, clat, clon


def nearest_grid(lon, lat, centers):
    """QGIS 격자 중심 목록(grid_id, lat, lon) 중 가장 가까운 격자 (격자 크기 안쪽만)"""
    import numpy as np
    cx, cy = meters(centers["lon"].values, centers["lat"].values)
    px, py = meters(lon.values, lat.values)
    ids = []
    for x, y in zip(px, py):
        d2 = (cx - x) ** 2 + (cy - y) ** 2
        k = int(np.argmin(d2))
        ids.append(centers["grid_id"].iloc[k] if d2[k] <= (CELL_M * 0.75) ** 2 else None)
    return pd.Series(ids, index=lon.index)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="운행내역 파일 (.xlsx 또는 .csv)")
    ap.add_argument("--sites", help="후보 거점 CSV (site_id,name,lat,lon,capacity)")
    ap.add_argument("--grid-centers", help="QGIS 격자 중심 CSV (grid_id,lat,lon)")
    ap.add_argument("--all-days", action="store_true", help="주말도 포함")
    ap.add_argument("--n-temp-sites", type=int, default=15, help="임시 후보 거점 수")
    a = ap.parse_args()

    src = Path(a.src)
    df = pd.read_excel(src) if src.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(src, encoding="utf-8-sig")
    print(f"원본 {len(df):,}건 / 열: {list(df.columns)}")
    missing = [v for v in COL.values() if v not in df.columns]
    if missing:
        sys.exit(f"원본에 없는 열: {missing}\n→ 이 파일 맨 위 COL의 오른쪽 이름을 원본 열 이름으로 바꿔 주세요.")

    df["접수"] = pd.to_datetime(df[COL["접수"]], errors="coerce")
    df["승차"] = pd.to_datetime(df[COL["승차"]], errors="coerce")
    n0 = len(df)
    df = df[~df[COL["예약"]].astype(str).str.strip().isin(RESERVED_VALUES)]           # 즉시콜만
    df = df[df["접수"].notna()]
    df = df[~(df["승차"] < df["접수"])]                                               # 기입 오류
    if not a.all_days:
        df = df[df["접수"].dt.dayofweek < 5]                                          # 평일만
    df = df.dropna(subset=[COL["출발X"], COL["출발Y"]])
    df["slot"] = df["접수"].dt.hour.map(slot_of)
    df = df[df["slot"].notna()]
    print(f"정제 후 {len(df):,}건 (제외 {n0 - len(df):,}건: 예약콜·주말·오류·시간대 밖)")

    olon, olat = to_lonlat(df[COL["출발X"]].astype(float), df[COL["출발Y"]].astype(float))
    has_dest = df[COL["도착X"]].notna() & df[COL["도착Y"]].notna()
    dlon, dlat = to_lonlat(df.loc[has_dest, COL["도착X"]].astype(float), df.loc[has_dest, COL["도착Y"]].astype(float))

    if a.grid_centers:
        centers = pd.read_csv(a.grid_centers, encoding="utf-8-sig")
        df["o_grid"] = nearest_grid(olon, olat, centers)
        df.loc[has_dest, "d_grid"] = nearest_grid(dlon, dlat, centers)
        grids = centers[["grid_id", "lat", "lon"]]
    else:
        df["o_grid"], oc_lat, oc_lon = auto_grid(olon, olat)
        dg, dc_lat, dc_lon = auto_grid(dlon, dlat)
        df.loc[has_dest, "d_grid"] = dg
        grids = pd.concat([pd.DataFrame(dict(grid_id=df["o_grid"], lat=oc_lat, lon=oc_lon)),
                           pd.DataFrame(dict(grid_id=dg, lat=dc_lat, lon=dc_lon))]).drop_duplicates("grid_id")

    days = df["접수"].dt.normalize().nunique()
    print(f"집계 일수 {days}일 (하루 평균으로 나눔)")

    demand = (df.dropna(subset=["o_grid"]).groupby(["o_grid", "slot"]).size() / days).round(3)
    demand = demand.rename("calls").reset_index().rename(columns={"o_grid": "grid_id"})

    done = df[df[COL["결과"]].astype(str).str.contains(DONE_VALUE, na=False)].dropna(subset=["o_grid", "d_grid"])
    od = (done.groupby(["slot", "o_grid", "d_grid"]).size() / days).round(3)
    od = od.rename("trips").reset_index().rename(columns={"o_grid": "origin_grid", "d_grid": "dest_grid"})

    if a.sites:
        sites = pd.read_csv(a.sites, encoding="utf-8-sig")
    else:   # 임시: 하차(도착)가 가장 많은 격자 = 빈 차가 자주 생기는 곳
        drops = done.groupby("d_grid").size().sort_values(ascending=False).head(a.n_temp_sites)
        g = grids.set_index("grid_id")
        cap = int(demand.groupby("slot")["calls"].sum().max()) + 1     # 임시라 용량 제약은 느슨하게
        sites = pd.DataFrame([dict(site_id=f"T{k + 1:02d}", name=f"임시 후보(하차 다발 격자 {gid})",
                                   lat=g.loc[gid, "lat"], lon=g.loc[gid, "lon"], capacity=cap)
                              for k, gid in enumerate(drops.index)])
        print("※ --sites가 없어 '하차가 많은 격자'로 임시 후보 거점을 만들었어요. 병원·복지관 목록이 생기면 교체하세요.")

    OUT.mkdir(parents=True, exist_ok=True)
    grids.to_csv(OUT / "grids.csv", index=False, encoding="utf-8-sig")
    demand.to_csv(OUT / "demand.csv", index=False, encoding="utf-8-sig")
    od.to_csv(OUT / "od.csv", index=False, encoding="utf-8-sig")
    sites.to_csv(OUT / "sites.csv", index=False, encoding="utf-8-sig")
    print(f"저장 완료 → {OUT}\n  격자 {len(grids)}개, 수요 {len(demand)}행, 이동 {len(od)}행, 후보 거점 {len(sites)}곳")


if __name__ == "__main__":
    main()
