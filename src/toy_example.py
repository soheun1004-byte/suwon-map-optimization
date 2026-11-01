"""
손으로 푼 예시(동네 3개, 후보 3곳, P=2)를 그대로 코드로 옮긴 연습용 파일
정답: 후보 1, 2 선정 / 합 120 / 평균 6분
실행: python toy_example.py
"""
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds

# ---------- 1. 입력값 (모델이 정하는 게 아니라 우리가 넣어주는 것) ----------
d = np.array([10, 4, 6])            # 호출 수: A, B, C
tau = np.array([[5, 25, 15],        # 이동시간(분): 행=동네 i, 열=후보 j
                [15, 10, 5],        #   A행: 후보1 5분, 후보2 25분, 후보3 15분
                [25, 5, 15]])
U = np.array([100, 100, 100])       # 거점 용량 (넉넉하게)
P = 2                               # 열 거점 수
N_I, N_J = 3, 3
nx = N_I * N_J                      # x 변수 개수 = 9

# ---------- 2. 변수를 한 줄로 펼치기 ----------
# [x(A,1) x(A,2) x(A,3) x(B,1) x(B,2) x(B,3) x(C,1) x(C,2) x(C,3) | z1 z2 z3]
# x(i,j)는 i*N_J + j 번째 칸, z(j)는 nx + j 번째 칸

# ---------- 3. 목적함수: min Σ d·τ·x ----------
c = np.concatenate([(d[:, None] * tau).ravel(), np.zeros(N_J)])
print("목적함수 계수 c:", c)

# ---------- 4. 제약식: 한 줄(row) = 제약식 하나 ----------
A, lb, ub = [], [], []
# (1) 모든 동네는 배정: x(i,1)+x(i,2)+x(i,3) = 1
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
# (4) 거점 수: z1+z2+z3 = P
row = np.zeros(nx + N_J); row[nx:] = 1
A.append(row); lb.append(P); ub.append(P)

# ---------- 5. 풀기 ----------
integrality = np.concatenate([np.zeros(nx), np.ones(N_J)])   # x는 실수, z만 정수
res = milp(c, constraints=LinearConstraint(np.array(A), lb, ub),
           integrality=integrality, bounds=Bounds(0, 1))

# ---------- 6. 결과 읽기 ----------
x = res.x[:nx].reshape(N_I, N_J).round(2)
z = res.x[nx:].round().astype(int)
print("z (열린 거점):", z, "→ 후보", [j + 1 for j in range(N_J) if z[j] == 1])
for i, name in enumerate("ABC"):
    print(f"  {name} 동네 → 후보 {x[i].argmax() + 1}  (x 행: {x[i]})")
print("합:", res.fun, "/ 평균:", res.fun / d.sum(), "분")
