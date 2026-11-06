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

---

# 2주차 스키마 연동 (9주차 추가)

`control-system-schema` 저장소의 메시지 형식(`schema.json`)과 DB 테이블(`schema.sql`)을 `schema/` 폴더로 가져와 API에 연결함.

| 메서드 | 주소 | 용도 | 누가 부르나 |
|---|---|---|---|
| POST | `/api/messages` | 위치·상태 메시지 수신 → `schema.json` 검사 → `vehicle_logs` 저장 | 운전원 앱 |
| GET | `/api/vehicles` | 차량별 최신 위치·상태 | 관제 대시보드 |
| GET | `/api/recommend?lat=&lon=` | 현재 위치에서 갈 대기 거점 추천 (`slot`, `P`, `vehicleId` 선택) | 운전원 앱 / 대시보드 |

## 운전원 앱 연동 흐름
1. 운행 중 위치·상태를 `POST /api/messages`로 보냄
2. **승객 하차 후** `status: "IDLE"`로 보내면 응답의 `recommendation`에 대기 거점이 옴
3. 앱은 `recommendation.site`(이름·좌표)를 지도에 표시: "○○로 이동해 대기"

요청 예시
```json
{"header": {"messageId": "m1", "senderId": "V007", "receiverId": "CONTROL", "timestamp": "2026-11-01T16:40:00+09:00"},
 "payload": {"vehicleId": "V007", "status": "IDLE", "latitude": 37.2665, "longitude": 127.0002}}
```
응답 (201)
```json
{"saved": true, "log_id": 1,
 "recommendation": {"slot": "15-18", "P": 4, "travel_min": 4.1,
   "site": {"site_id": "S01", "name": "예시 거점 1", "lat": 37.2763, "lon": 127.0110, "capacity": 104},
   "command": {"header": {"senderId": "CONTROL", "receiverId": "V007", "...": "..."},
               "payload": {"vehicleId": "V007", "status": "IDLE", "targetSiteId": "S01", "latitude": 37.2763, "longitude": 127.0110}}}}
```
- `command`는 관제→운전원 지시를 **2주차 형식 그대로** 만든 것 (앱이 그대로 받아 쓸 수 있음)
- 형식이 틀리면 400 + `details`에 어느 칸이 틀렸는지 나옴

## 스키마 변경점 (2주차 → 9주차)
- `status`에 **`IDLE`**(승객 하차 후 빈 차 대기) 추가
- `payload`에 **`targetSiteId`**(이동해서 대기할 거점 ID, 선택) 추가
- DB는 개발용으로 SQLite(`schema/schema_sqlite.sql`, 파일 `data/processed/app.db`) 사용. 실서버는 `schema/schema.sql`(PostgreSQL) 그대로 쓰면 됨

## 임시 규칙 (나중에 바꿀 것)
- 추천 시간대: 현재 시각이 09~12시면 `09-12`, 15~18시면 `15-18`, 그 밖은 `09-12`
- 거점 수 P: 4
- 추천 = 그 시간대에 선정된 거점 중 현재 위치에서 가장 가까운 곳 (다른 빈 차가 이미 가 있는지는 아직 안 봄)

---

# 수요 분석 및 선제 배치 계획 화면 (10주차 추가)

> 가현이 화면의 3개 영역에 그대로 대응. 모두 `slot`(시간대)을 받으니 화면 위쪽 시간대 선택과 연결하면 됨.
> 시간대 목록은 `GET /api/slots`. 실데이터를 넣으면 `06-09, 09-12, 12-15, 15-18, 18-21` 5개가 됨.

| 화면 영역 | 메서드·주소 | 화면에 그릴 것 |
|---|---|---|
| ① 시간대별 이동 패턴 | `GET /api/patterns?slot=09-12&top=10` | 출발 집중 격자(`top_origins`), 도착 집중 격자(`top_destinations`), 주요 경로 화살표(`top_flows`), 주거지·주요 목적지 추정(`places`) |
| ② 시간대별 수요 전망 | `GET /api/forecast?slot=09-12&P=4` | 격자 히트맵(`grids.expected_calls`), 수요 증가 예상 격자 강조(`rising_grids`), 선제 배치 제안 거점(`suggested_sites`) |
| ③ 차량 배치 계획 | `GET /api/plan?slot=09-12&P=4&vehicles=20` | 거점별 배치 대수·근거(`sites`), 빈 차별 이동 지시 표(`moves`) |

## ① GET /api/patterns
```json
{"slot": "09-12", "total_trips": 100.0,
 "top_origins": [{"grid_id": "G010", "lat": 37.27, "lon": 127.00, "trips": 9.5, "share": 0.095}],
 "top_destinations": [{"grid_id": "G022", "lat": 37.28, "lon": 127.03, "trips": 8.0, "share": 0.08}],
 "top_flows": [{"origin": "G010", "dest": "G022", "trips": 1.5, "origin_lat": 37.27, "origin_lon": 127.00, "dest_lat": 37.28, "dest_lon": 127.03, "km": 2.9}],
 "places": {"morning_slot": "09-12", "afternoon_slot": "15-18",
            "homes": [{"grid_id": "G010", "lat": 37.27, "lon": 127.00, "score": 0.08}],
            "destinations": [{"grid_id": "G025", "lat": 37.29, "lon": 127.02, "score": 0.07}]}}
```
- `trips`: 하루 평균 통행 수, `share`: 그 시간대 전체 통행 중 비율
- `places`: 오전에 나가고 오후에 돌아오는 격자 = 주거지 후보, 그 반대 = 주요 목적지 후보 (추정)
- od.csv가 없는 시간대를 넣으면 400

## ② GET /api/forecast
```json
{"slot": "15-18", "method": "과거 동일 시간대 평균 (v0.1)", "total_expected_calls": 180.0, "top_share": 0.19,
 "grids": [{"grid_id": "G023", "lat": 37.28, "lon": 127.02, "expected_calls": 6.0, "usual_calls": 4.0, "ratio": 1.5, "rising": true}],
 "top_grids": ["...호출 많은 순 상위 top개..."],
 "rising_grids": ["...평소보다 1.2배 이상 늘어나는 격자..."],
 "suggested_sites": [{"site_id": "S01", "name": "예시 거점 1", "lat": 37.27, "lon": 127.01, "capacity": 104}]}
```
- `expected_calls`: 그 시간대 예상 호출 수 (과거 같은 시간대 하루 평균)
- `usual_calls`: 그 격자의 전체 시간대 평균, `ratio` = expected ÷ usual
- `rising`: ratio ≥ 1.2 이고 예상 호출 ≥ 1건 → **화면에서 색으로 강조**
- `suggested_sites`: 이 시간대에 p-median이 고른 대기 거점 = 선제 배치 제안 지역

## ③ GET /api/plan
```json
{"status": "optimal", "slot": "09-12", "P": 4, "n_vehicles": 20, "avg_travel_min": 3.52,
 "vehicle_source": "vehicles 파라미터",
 "sites": [{"site_id": "S05", "name": "예시 거점 5", "lat": 37.24, "lon": 127.03, "capacity": 114,
            "load": 90.0, "vehicles": 7, "covers": ["G007", "G009", "G033"],
            "reason": "예상 호출 90.0건을 맡음 (주요 격자: G007, G009, G033)"}],
 "moves": [{"vehicle_id": "V009", "target_site_id": "S05", "travel_min": 4.2}]}
```
- `vehicles`: 그 거점에 대기시킬 차량 대수 (맡는 호출 수 비율대로 나눔)
- `reason`: 관제사에게 보여줄 근거 문장
- `moves`: 운전원 앱에서 `IDLE`(빈 차)로 보고된 차가 있을 때만 채워짐. 가까운 차부터 자리가 남은 거점으로 배정
  - 빈 차 보고가 없으면 `vehicles=20`처럼 대수만 넣어서 계획을 볼 수 있음 (`vehicle_source`로 구분)
- 관제사가 이동 지시를 승인하면, 운전원 앱에는 `/api/recommend`가 만드는 2주차 형식 `command`를 보내면 됨

## 실데이터 넣기
```bash
pip install -r requirements.txt
python tools/build_csvs.py 운행내역.xlsx            # data/processed/에 CSV 4개 생성
python src/api.py                                   # /api/health 에서 data_source가 processed면 성공
```
