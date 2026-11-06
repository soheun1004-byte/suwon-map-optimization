# 수원이가 좋아할 지도 — 교통약자 특별교통수단 빈 차 대기 거점 최적화

2026-2 아주대학교 파란학기제 (Extreme) · 팀 **수원이가 좋아할 지도**
도전과제: 수원시 교통약자지원센터 차량 배차 개선을 통한 고객 대기시간 감소 방안

## 구성
| 경로 | 내용 |
|---|---|
| `docs/model.md` | 모델 명세 (문제 정의, p-median 수식, 진행 상태) |
| `docs/mapping_rules.md` | 입력 변수 매핑 규칙 및 데이터 정제 기준 |
| `docs/api.md` | 대시보드용 REST API 명세 (9-10주차) |
| `src/pmedian_prototype.py` | 8주차 프로토타입 (예시 데이터 + 그림) |
| `src/engine.py` | 선제 배치 알고리즘 엔진 (p-median 코어, scipy MILP / HiGHS) |
| `src/pipeline.py` | 데이터 공급 파이프라인 (CSV → 엔진 입력 d, τ, U) |
| `src/api.py` | 관제 대시보드용 REST API (Flask) |
| `src/db.py` | 2주차 스키마 연동: 메시지 검사(`schema.json`) + 저장(`vehicle_logs`) |
| `schema/` | 2주차 송수신 스키마(`schema.json`, `schema.sql`) + SQLite 개발용 버전 |
| `src/analysis.py` | 수요 분석 및 선제 배치 계획 화면용 계산 (이동 패턴, 수요 전망, 배치 계획) |
| `tools/build_csvs.py` | 운행내역 원본 → grids/demand/od/sites CSV 변환 |
| `tests/` | 유닛 테스트 (손계산 예제로 엔진 검증) + API 테스트 |
| `results/pmedian_prototype.png` | 프로토타입 결과 그림 |
| `results/run_log.txt` | 실행 로그 (선정 거점, 평균 도착시간, 연산 시간) |
| `data/` | 원본 운행내역은 개인 이동정보가 포함되어 **업로드하지 않음** |

## 실행
```bash
pip install -r requirements.txt
python -m pytest -v              # 테스트 (31개)
python src/pmedian_prototype.py  # 8주차 프로토타입 그림
python src/api.py                # API 서버 → http://127.0.0.1:5000/api/health
```

> ⚠️ 현재 결과는 **예시(난수) 데이터**로 모델 구조와 연산 시간을 확인한 것입니다. 실제 운행내역 적용 결과는 이후 업데이트합니다.

## 진행 기록
- 8주차: 모델 명세 v0.1, 프로토타입 코드 업로드
- 9주차: 엔진 모듈 분리, 1차 유닛 테스트, REST API·데이터 파이프라인 골격 (현재 예시 데이터로 동작)
- 9주차: 2주차 관제-운전원 스키마 통합 (메시지 검사·저장, 차량 조회, 빈 차 대기 거점 추천 API)
- 10주차: 수요 분석 및 선제 배치 계획 화면용 API 3개(/api/patterns, /api/forecast, /api/plan), 운행내역→CSV 변환 스크립트
