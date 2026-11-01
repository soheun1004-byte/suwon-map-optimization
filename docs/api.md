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
