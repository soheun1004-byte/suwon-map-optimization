"""
1차 유닛 테스트: 손으로 정답을 구할 수 있는 작은 문제를 넣고, 엔진이 그 답을 내는지 확인
실행: python -m pytest -v

예시 문제 (동네 A·B·C, 후보 1·2·3, 거점 2개)
  호출 수     A=10, B=4, C=6
  이동시간    후보1: A 5,  B 15, C 25
              후보2: A 25, B 10, C 5
              후보3: A 15, B 5,  C 15
  손계산 정답: 후보 1·2 선정, 합 120 (=10×5 + 4×10 + 6×5), 평균 6분
"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from engine import solve_pmedian

D = [10, 4, 6]
TAU = [[5, 25, 15], [15, 10, 5], [25, 5, 15]]
BIG_U = [100, 100, 100]


def test_hand_calculated_answer():
    r = solve_pmedian(D, TAU, BIG_U, P=2)
    assert r["status"] == "optimal"
    assert r["open_sites"] == [0, 1]              # 후보 1, 2
    assert r["total"] == pytest.approx(120)
    assert r["avg_min"] == pytest.approx(6)


def test_each_area_goes_to_nearest_open_site():
    r = solve_pmedian(D, TAU, BIG_U, P=2)
    assert sorted(r["assign"]) == [(0, 0, 1.0), (1, 1, 1.0), (2, 1, 1.0)]  # A→1, B→2, C→2


def test_opens_exactly_P_sites():
    for P in (1, 2, 3):
        assert len(solve_pmedian(D, TAU, BIG_U, P)["open_sites"]) == P


def test_P1_picks_best_single_site():
    # 후보1: 10·5+4·15+6·25=260 / 후보2: 250+40+30=320 / 후보3: 150+20+90=260 → 260
    assert solve_pmedian(D, TAU, BIG_U, P=1)["total"] == pytest.approx(260)


def test_capacity_splits_demand():
    # 후보1 용량 6 → A 호출 10건 중 6건만 후보1, 4건은 후보2(25분)
    r = solve_pmedian(D, TAU, [6, 100, 100], P=2)
    a = {(i, j): s for i, j, s in r["assign"]}
    assert a[(0, 0)] == pytest.approx(0.6) and a[(0, 1)] == pytest.approx(0.4)
    assert r["total"] == pytest.approx(200)       # 6×5 + 4×25 + 40 + 30


def test_every_area_fully_assigned():
    r = solve_pmedian(D, TAU, [6, 100, 100], P=2)
    for i in range(3):
        assert sum(s for ii, _, s in r["assign"] if ii == i) == pytest.approx(1)


def test_infeasible_when_capacity_too_small():
    r = solve_pmedian(D, TAU, [5, 5, 5], P=2)     # 용량 합 10 < 호출 20
    assert r["status"] == "infeasible"


def test_bad_input_raises():
    with pytest.raises(ValueError):
        solve_pmedian(D, TAU, BIG_U, P=5)         # 후보는 3곳뿐
    with pytest.raises(ValueError):
        solve_pmedian([1, 2], TAU, BIG_U, P=2)    # d 길이 틀림
