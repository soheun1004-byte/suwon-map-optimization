# 수원이가 좋아할 지도 — 교통약자 특별교통수단 빈 차 대기 거점 최적화

2026-2 아주대학교 파란학기제 (Extreme) · 팀 **수원이가 좋아할 지도**
도전과제: 수원시 교통약자지원센터 차량 배차 개선을 통한 고객 대기시간 감소 방안

## 구성
| 경로 | 내용 |
|---|---|
| `docs/model.md` | 모델 명세 (문제 정의, p-median 수식, 진행 상태) |
| `docs/mapping_rules.md` | 입력 변수 매핑 규칙 및 데이터 정제 기준 |
| `docs/면담_사전자료.pdf` | 지도교수님 면담 사전자료 |
| `src/pmedian_prototype.py` | 시간대별 용량 제약 p-median 프로토타입 (scipy MILP / HiGHS) |
| `results/pmedian_prototype.png` | 프로토타입 결과 그림 |
| `results/run_log.txt` | 실행 로그 (선정 거점, 평균 도착시간, 연산 시간) |
| `data/` | 원본 운행내역은 개인 이동정보가 포함되어 **업로드하지 않음** |

## 실행
```bash
pip install numpy scipy matplotlib
python src/pmedian_prototype.py
```

> ⚠️ 현재 결과는 **예시(난수) 데이터**로 모델 구조와 연산 시간을 확인한 것입니다. 실제 운행내역 적용 결과는 이후 업데이트합니다.

## 진행 기록
- 8주차: 모델 명세 v0.1, 프로토타입 코드 업로드
