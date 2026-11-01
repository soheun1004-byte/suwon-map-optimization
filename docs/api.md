# 백엔드 REST API 명세 (v0.1, 9-10주차)

> 대시보드 담당자용. 서버 실행: `python src/api.py` → 기본 주소 `http://127.0.0.1:5000`
> 모든 응답은 JSON. `data_source`가 `sample`이면 예시(난수) 데이터, `processed`면 실데이터.

| 메서드 | 주소 | 용도 | 대시보드 화면 |
|---|---|---|---|
| GET | `/api/health` | 서버 상태 | 연결 표시 |
| GET | `/api/slots` | 시간대 목록 `["09-12","15-18"]` | 시간대 선택 드롭다운 |
| GET | `/api/sites` | 후보 거점 `site_id, name, lat, lon, capacity` | 지도에 후보 표시 |
| GET | `/api/demand?slot=09-12` | 격자별 호출 수 `grid_id, lat, lon, calls` | 호출 히트맵 |
| POST | `/api/optimize` | 선정 거점 계산 | 추천 거점 표시 |

## POST /api/optimize
요청
```json
{"slot": "09-12", "P": 4}
```
응답 (200)
```json
{
  "status": "optimal", "data_source": "sample", "slot": "09-12", "P": 4,
  "avg_travel_min": 3.52, "solve_sec": 0.02,
  "open_sites": [{"site_id": "S05", "name": "예시 거점 5", "lat": 37.2419, "lon": 127.0347, "capacity": 114, "load": 90.0}],
  "assignments": [{"grid_id": "G000", "site_id": "S11", "share": 1.0}]
}
```
- `open_sites.load`: 그 거점이 맡게 된 호출 수 (capacity와 비교하면 여유 확인 가능)
- `assignments.share`: 격자 호출 중 그 거점이 맡는 비율 (용량이 넘칠 때만 1보다 작음)
- 오류: 잘못된 slot·P → 400 / 해 없음(용량 부족) → 422

## 데이터 흐름
```
운행내역(비공개) ─▶ data/processed/{grids,demand,sites}.csv ─▶ pipeline.py ─▶ engine.py ─▶ api.py ─▶ 대시보드
```
CSV 형식은 `src/pipeline.py` 맨 위 설명 참고.
