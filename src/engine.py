"""
선제 배치 알고리즘 엔진 (시간대별 용량 제약 p-median의 한 시간대)

pmedian_prototype.py의 solve()에서 '푸는 부분'만 떼어낸 것.
데이터를 안에서 만들지 않고 밖에서 받기 때문에 API, 테스트, 실데이터 어디서든 재사용 가능.

입력
  d   : (I,)   격자별 호출 수
  tau : (I, J) 격자 i ↔ 거점 j 이동시간(분)
  U   : (J,)   거점별 용량(감당 가능한 호출 수)
  P   : int    열 거점 수
출력 (dict)
  status       "optimal" / "infeasible" / "error"
  open_sites   선정된 거점 번호 리스트 (z=1)
  assign       [(격자 i, 거점 j, 비율 x)] — 비율이 0보다 큰 것만
  total        목적함수 값 Σ d·τ·x
  avg_min      평균 이동시간 = total / Σd
  solve_sec    푸는 데 걸린 시간(초)
"""
import time
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds


def solve_pmedian(d, tau, U, P, time_limit=60):
    d = np.asarray(d, dtype=float)
    tau = np.asarray(tau, dtype=float)
    U = np.asarray(U, dtype=float)
    N_I, N_J = tau.shape
    if d.shape != (N_I,) or U.shape != (N_J,):
        raise ValueError(f"크기 불일치: d{d.shape}, tau{tau.shape}, U{U.shape}")
    if not 1 <= P <= N_J:
        raise ValueError(f"P는 1~{N_J} 사이여야 함 (받은 값 {P})")

    nx = N_I * N_J
    # 변수 순서: [x(0,0) … x(0,J-1) | x(1,0) … | … | z(0) … z(J-1)]
    c = np.concatenate([(d[:, None] * tau).ravel(), np.zeros(N_J)])

    A, lb, ub = [], [], []
    # (1) 모든 격자는 배정: Σ_j x(i,j) = 1
    for i in range(N_I):
        row = np.zeros(nx + N_J); row[i*N_J:(i+1)*N_J] = 1
        A.append(row); lb.append(1); ub.append(1)
    # (2) 연 거점에만 배정: x(i,j) - z(j) <= 0
    for i in range(N_I):
        for j in range(N_J):
            row = np.zeros(nx + N_J); row[i*N_J + j] = 1; row[nx + j] = -1
            A.append(row); lb.append(-np.inf); ub.append(0)
    # (3) 용량: Σ_i d(i)·x(i,j) - U(j)·z(j) <= 0
    for j in range(N_J):
        row = np.zeros(nx + N_J); row[j:nx:N_J] = d; row[nx + j] = -U[j]
        A.append(row); lb.append(-np.inf); ub.append(0)
    # (4) 거점 수: Σ_j z(j) = P
    row = np.zeros(nx + N_J); row[nx:] = 1
    A.append(row); lb.append(P); ub.append(P)

    integrality = np.concatenate([np.zeros(nx), np.ones(N_J)])  # z만 정수
    t0 = time.perf_counter()
    res = milp(c, constraints=LinearConstraint(np.array(A), lb, ub),
               integrality=integrality, bounds=Bounds(0, 1),
               options={"time_limit": time_limit})
    sec = time.perf_counter() - t0

    if res.x is None:  # 해가 없음 (예: 용량 합이 수요보다 작음)
        status = "infeasible" if res.status == 2 else "error"
        return dict(status=status, message=res.message, open_sites=[], assign=[],
                    total=None, avg_min=None, solve_sec=sec)

    x = res.x[:nx].reshape(N_I, N_J)
    z = res.x[nx:].round().astype(int)
    assign = [(i, j, round(float(x[i, j]), 4))
              for i in range(N_I) for j in range(N_J) if x[i, j] > 1e-6]
    total = float(res.fun)
    return dict(status="optimal", message=res.message,
                open_sites=[int(j) for j in np.where(z == 1)[0]],
                assign=assign, total=total, avg_min=total / d.sum(), solve_sec=sec)
