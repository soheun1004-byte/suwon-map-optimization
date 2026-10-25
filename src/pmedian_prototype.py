"""
시간대별 용량 제약 p-median 프로토타입 (예시 데이터)

- 목적: 빈 차 대기 거점 선정 모델의 구조가 실제로 풀리는지 확인
- 데이터: 실제 운행내역이 아닌 '예시 데이터'(난수로 만든 격자·거점)
- 실제 데이터 적용은 9~10주차 예정

실행: python src/pmedian_prototype.py
"""
import time
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
for _f in ["Noto Sans CJK KR", "NanumGothic", "Malgun Gothic", "AppleGothic"]:
    if any(_f == f.name for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = _f; break

rng = np.random.default_rng(2026)

# ---------- 1. 예시 데이터 ----------
N_I = 40        # 호출 지역(격자) 수
N_J = 12        # 후보 거점 수 (병원·복지관 주차장 가정)
P = 4           # 시간대별 운영 거점 수
SLOTS = ["09-12", "15-18"]
SPEED = {"09-12": 0.45, "15-18": 0.35}   # km/분 (체증 반영 가정)

hot = np.array([[3, 7], [7, 3], [6, 8]])
demand_xy = np.vstack([hot[rng.integers(0, 3, N_I)] + rng.normal(0, 1.4, (N_I, 2))])
demand_xy = np.clip(demand_xy, 0, 10)
cand_xy = rng.uniform(0.5, 9.5, (N_J, 2))
base = {"09-12": rng.poisson(6, N_I) + 1, "15-18": rng.poisson(4, N_I) + 1}
U = rng.integers(70, 120, N_J)            # 거점별 처리 가능 호출 수(용량)

dist = np.linalg.norm(demand_xy[:, None, :] - cand_xy[None, :, :], axis=2)  # km


def solve(slot):
    d = base[slot].astype(float)
    tau = dist / SPEED[slot]                    # 분
    nx = N_I * N_J
    # 변수: x[i,j] (0~1, 할당 비율), z[j] (0/1, 거점 운영)
    c = np.concatenate([(d[:, None] * tau).ravel(), np.zeros(N_J)])
    A, lb, ub = [], [], []
    # (1) 모든 호출 지역은 한 곳 이상에 배정: sum_j x_ij = 1
    for i in range(N_I):
        row = np.zeros(nx + N_J); row[i*N_J:(i+1)*N_J] = 1
        A.append(row); lb.append(1); ub.append(1)
    # (2) 운영하는 거점에만 배정: x_ij - z_j <= 0
    for i in range(N_I):
        for j in range(N_J):
            row = np.zeros(nx + N_J); row[i*N_J+j] = 1; row[nx+j] = -1
            A.append(row); lb.append(-np.inf); ub.append(0)
    # (3) 용량: sum_i d_i x_ij - U_j z_j <= 0
    for j in range(N_J):
        row = np.zeros(nx + N_J)
        row[j:nx:N_J] = d; row[nx+j] = -U[j]
        A.append(row); lb.append(-np.inf); ub.append(0)
    # (4) 거점 수: sum_j z_j = P
    row = np.zeros(nx + N_J); row[nx:] = 1
    A.append(row); lb.append(P); ub.append(P)

    integrality = np.concatenate([np.zeros(nx), np.ones(N_J)])
    t0 = time.perf_counter()
    res = milp(c, constraints=LinearConstraint(np.array(A), lb, ub),
               integrality=integrality, bounds=Bounds(0, 1))
    sec = time.perf_counter() - t0
    x = res.x[:nx].reshape(N_I, N_J); z = res.x[nx:].round().astype(int)
    avg = (d[:, None] * tau * x).sum() / d.sum()
    return dict(slot=slot, status=res.message, z=z, x=x, avg_min=avg, sec=sec, d=d)


def baseline(slot):
    """비교용: 차고지(왼쪽 아래 한 곳)에서만 출동한다고 가정"""
    depot = np.array([1.0, 1.0])
    d = base[slot]
    t = np.linalg.norm(demand_xy - depot, axis=1) / SPEED[slot]
    return (d * t).sum() / d.sum()


if __name__ == "__main__":
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2), dpi=160)
    lines = []
    for ax, slot in zip(axes, SLOTS):
        r = solve(slot); b = baseline(slot)
        line = (f"[{slot}] 상태: {r['status']} | 선정 거점: {[int(j) for j in np.where(r['z']==1)[0]]} | "
                f"평균 도착시간 {r['avg_min']:.1f}분 (차고지 단일 출동 가정 {b:.1f}분) | 연산 {r['sec']:.2f}초")
        print(line); lines.append(line)
        open_j = np.where(r["z"] == 1)[0]
        for i in range(N_I):
            j = r["x"][i].argmax()
            ax.plot([demand_xy[i,0], cand_xy[j,0]], [demand_xy[i,1], cand_xy[j,1]], color="#bbb", lw=0.8, zorder=1)
        ax.scatter(demand_xy[:,0], demand_xy[:,1], s=r["d"]*8, color="#4a7bd0", alpha=.7, label="호출 지역 (크기=호출 수)", zorder=2)
        closed = [j for j in range(N_J) if j not in open_j]
        ax.scatter(cand_xy[closed,0], cand_xy[closed,1], marker="s", s=60, facecolor="white", edgecolor="#999", label="후보 거점(미선정)", zorder=3)
        ax.scatter(cand_xy[open_j,0], cand_xy[open_j,1], marker="s", s=110, color="#e8742a", label="선정 거점", zorder=4)
        ax.scatter([1],[1], marker="^", s=120, color="#333", label="차고지", zorder=4)
        ax.set_title(f"{slot}시  |  평균 도착 {r['avg_min']:.1f}분 (차고지만: {b:.1f}분)", fontsize=10)
        ax.set_xlim(0,10); ax.set_ylim(0,10); ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=4, fontsize=9, frameon=False)
    fig.suptitle("시간대별 용량 제약 p-median 프로토타입 (예시 데이터, P=4)", fontsize=12)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig("results/pmedian_prototype.png")
    open("results/run_log.txt", "w").write("\n".join(lines) + "\n※ 예시 데이터 결과이며 실제 운행내역 결과가 아님\n")
