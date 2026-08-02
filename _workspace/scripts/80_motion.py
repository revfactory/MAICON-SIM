# -*- coding: utf-8 -*-
"""
80_motion.py — UGV 주행 경로 + 애니메이션 (motion-director 산출)

산출물
    PATH_Main                베지어 주행 커브 (열린 경로, START -> FINISH)
    UGV_Root                 Follow Path 컨스트레인트 + eval_time 속도 곡선
    UGV_Wheel_{FL,FR,RL,RR}  이동 거리에서 계산한 굴림 회전 (좌우 차동) + 앞바퀴 조향
    UGV_Body / UGV_Sensor    코너 롤 / 회피 롤 부스트 / 가감속 피치 / 노면 진동
    spec/timeline.json       체크포인트·회피 이벤트 프레임 (실측값)

--------------------------------------------------------------------------
설계 메모
--------------------------------------------------------------------------
1) 제어점(PATH_PTS, 28점)은 스펙 path 22점을 출발점으로 삼되 **태그 5점
   (START/ALPHA/BRAVO/CHARLIE/FINISH)은 좌표 그대로** 두고 태그 없는 점만
   (a) 회랑(블록 사이 도로) 중앙으로 당기고 (b) 하자드 회피가 눈에 보이도록
   재배치했다. 스크립트 시작에서 태그 점이 스펙과 일치하는지 assert 로 검산한다.

   접선은 "세 점의 외접원" 규칙으로 잡는다 — 원호를 정확히 재현하므로 코너가
   실제 주행선처럼 나온다. 핸들 길이는 h = |c| / (3 cos^2(a/2)) 원호 근사값.
   핸들 타입을 AUTO 로 두지 않고 FREE + 명시 좌표로 넣는 이유는, 그래야
   스크립트가 계산한 곡선과 블렌더가 그리는 곡선이 정확히 같아져서 아래의
   클리어런스 검산이 의미를 갖기 때문이다.

2) 차선 구조 (20_markings.py 기준): 노란 선은 각 블록의 **경계선**이고
   블록 사이 간격이 도로다. 실측 회랑 폭 —
       내부  A|B 0.240   D|E 0.280   A|D 0.260   B|E 0.260
       외곽  좌 0.330   우 0.330   하 0.370   상 0.440
   UGV 차폭 0.130 이므로 가장 좁은 A|B 0.240 에서도 좌우 0.055 씩 남는다.
   CORRIDORS 표로 샘플별 중앙선 이탈을 재서 timeline.json 에 남긴다.

3) 클리어런스는 두 단계로 본다.
     - repair()  중심선 기준 (측량사와 동일한 방식: 거리 - 차폭 절반)
     - 최종 검산  실제 차체 실루엣 스윕. 헐 4모서리 + 뒷바퀴 4모서리 +
                  **조향각을 반영한 앞바퀴 4모서리**
   측량사의 폴리라인 검산은 차체 회전을 고려하지 않는다. 코너에서 차체가 돌면
   모서리가 바깥으로 더 나가고, 앞바퀴를 꺾으면 횡방향으로 더 나간다.
   조향 애니메이션을 넣었으므로 그 폭도 검산에 포함해야 정직한 값이 된다.

4) BRAVO 헤어핀의 곡률 반경은 0.25 m 를 만족할 수 없다. 기하학적 상한이다.
   BRAVO(-0.39,-0.13) 를 지나면서 SEC6 풋프린트 모서리(-0.163,-0.005) 를
   0.085 m 띄우는 원의 최대 반경은 0.143 m 다. 게다가 이 코너는
   "SEC6 클리어런스 <-> 코너 반경" 이 정면으로 충돌한다 —
   진입점을 서쪽으로 옮길수록 SEC6 는 멀어지고 V 는 뾰족해진다.
       진입점 x=-0.15 : SEC6 0.019 m / R 0.124 m   (이전 판)
       진입점 x=-0.26 : SEC6 0.070 m / R 0.087 m   (이번 판)
   19 mm 는 렌더에서 "긁고 지나감"으로 보인다. 체크포인트 통과와 건물 회피를
   우선해 후자를 택했고, 해당 코너의 속도를 크게 낮춰 보완했다.
   (우회 토폴로지도 검토했다: BRAVO 남서쪽으로 크게 도는 경로는 포트홀1
    동쪽 가장자리 -0.92 와 객체4(-0.66,0.43,r0.047) 사이 폭 0.043 m 슬롯을
    지나야 해서 차폭 0.130 이 물리적으로 들어가지 않는다.)

5) 아레나 벽 최소 여유 0.0045 m 는 **FINISH 태그가 결정하는 상한**이다.
   FINISH(2.23,-1.68) 에서 노면 경계 y=-1.75 까지 0.070, 차체 반폭 0.065 →
   남는 값이 0.005 다. FINISH 를 옮기지 않는 한 이 값은 못 올린다.
   대신 "벽에 붙어 가는 거리"를 줄였다: 하단 직선을 회랑 중앙(y=-1.525)으로
   올리고 마지막 0.9 m 에서만 FINISH 높이로 활강한다.
       벽 여유 0.03 m 미만 구간 길이  3.78 m  ->  2.04 m

6) 속도는 손으로 찍은 키가 아니라 물리 프로파일에서 만든다.
     v_limit = min(V_MAX * 감속캡, sqrt(A_LAT / kappa))
     감속캡 = 체크포인트 딥 + **하자드 딥(포트홀/배리어)**
     전방/후방 패스로 종방향 가감속 한계 적용 -> s(t) 적분 -> eval_time 키
   하자드 딥은 좌우 비대칭이다 (진입 sigma 0.36 / 이탈 sigma 0.20).
   "미리 브레이크 -> 옆으로 비켜 통과 -> 곧바로 재가속" 이 읽히게 하기 위함.

7) 회피가 보이게 하는 3종 세트
     - 감속        : 6) 의 하자드 딥
     - 차체 롤     : 하자드 창(window) 안에서 롤 게인을 올린다. 최대치는
                     그대로 3° — 진폭이 아니라 "반응 문턱"을 낮추는 것이다.
                     방향은 선회 바깥쪽(원심력) 그대로다.
     - 조향/구동   : 앞바퀴를 rotation_euler[2] 로 꺾고(최대 15°),
                     네 바퀴의 굴림을 좌우 차동으로 나눈다
                     (v_wheel = v - yaw_rate * y_wheel). 급코너에서 안쪽
                     바퀴가 눈에 띄게 느려진다 — 스키드 스티어의 실제 거동이고
                     "돌고 있다"가 가장 싸게 읽히는 신호다.

8) 차량 전방은 +X 다 (UGV_Root["forward_axis"]). forward_axis='FORWARD_X'.
   FORWARD_Y 로 두면 차가 옆으로 간다.
"""

import bpy
import json
import math
import os
import time

WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
exec(open(os.path.join(WORKSPACE, "scripts", "00_common.py")).read())

# ---------------------------------------------------------------- 타이밍 상수
FPS = 30
TOTAL_FRAMES = 720          # 24.0 s @30fps
HOLD_START = 20             # 출발 대기 (교전 개시 신호 대기)
HOLD_END = 25               # FINISH 정지 후 여운
DRIVE_F0 = 1 + HOLD_START           # 21
DRIVE_F1 = TOTAL_FRAMES - HOLD_END  # 695

# ---------------------------------------------------------------- 속도 곡선 상수
V_MAX = 1.02                # 직선 최고 속도 (스케일 전 기준값)
A_LAT = 0.75                # 횡가속 한계 -> 코너 속도 sqrt(A_LAT*R)
A_ACC = 0.80                # 종방향 가속 한계
A_DEC = 1.10                # 종방향 감속 한계 (브레이크가 더 강하다)
CP_DIP = 0.45               # 체크포인트에서 V_MAX 를 55% 로 제한
CP_SIG = 0.30               # 체크포인트 감속 구간 폭 (m, 가우시안 sigma)
HAZ_DIP = 0.50              # 하자드(포트홀/배리어)에서 V_MAX 를 50% 로 제한
HAZ_SIG_B = 0.36            # 하자드 진입측 폭 — 넓게 = 미리 브레이크
HAZ_SIG_A = 0.20            # 하자드 이탈측 폭 — 좁게 = 곧바로 재가속
KAP_WIN = 9                 # 곡률 max 필터 반폭 (코너 진입 전 미리 감속)

# ---------------------------------------------------------------- 부수 운동 상수
ROLL_MAX = math.radians(3.0)    # 코너 롤 최대 3도 (회피 부스트도 이 값을 못 넘는다)
PITCH_MAX = math.radians(2.0)   # 가감속 피치 최대 2도
A_LAT_REF = 0.55                # 롤이 최대치에 근접하는 횡가속
A_LON_REF = 0.55                # 피치가 최대치에 근접하는 종가속
AVOID_ROLL_GAIN = 2.2           # 회피 창 안에서 롤 반응 문턱을 1/(1+g) 로 낮춘다
SUSP_ALPHA = 0.18               # 서스펜션 1차 지연 (tau ~ 5.5 frame)
ROAD_NOISE_Z = 0.0005           # 노면 진동 0.5 mm
ROAD_NOISE_ROLL = math.radians(0.15)
POTHOLE_NOISE_Z = 0.0018        # 포트홀 근접 통과 시 추가 진동
POTHOLE_NOISE_ROLL = math.radians(0.5)
POTHOLE_NEAR = 0.45             # 이 거리 안이면 노면이 깨진 구간으로 본다

STEER_MAX = math.radians(15.0)  # 앞바퀴 최대 조향각 (실루엣 검산에 반영된다)
STEER_ALPHA = 0.25              # 조향 1차 지연 (조향기 응답)
AVOID_WINDOW = 0.55             # 하자드 회피 창 반경 (m, 호장 기준)

# ---------------------------------------------------------------- 검증 상수
CP_TOL = 0.05               # 체크포인트 통과 허용 오차
POTHOLE_MARGIN = 0.020      # 포트홀: r + 차폭절반 + 이 값
CLEAR_MARGIN = 0.020        # 그 외 장애물 중심선 여유
R_MIN_TARGET = 0.25         # 목표 최소 곡률 반경 (미달 시 경고 + 사유 기록)
WALL_INSET = 0.0045         # 차체 실루엣과 아레나 벽 사이 최소 간격 (5절 참조)
CURVE_RES_U = 24            # 커브 테셀레이션 (경로 호장 정확도)

SAMPLES_PER_SEG = 120       # repair 루프용 세그먼트 샘플 수
SAMPLES_FINAL = 240         # 최종 검산용
GRID_N = 1600               # 속도 프로파일 격자

# ---------------------------------------------------------------- 주행 제어점
# (x, y, tag)  tag 가 있는 점은 스펙 좌표 그대로 — 절대 움직이지 않는다.
# 태그 없는 점의 note 는 "왜 여기 있는가" 다. 수정 시 반드시 함께 갱신할 것.
PATH_PTS = [
    (-2.350,  1.3300, "START",   "출발선"),
    (-1.800,  1.4850, None,      "상단 회랑 중앙 y=1.49"),
    (-1.150,  1.6300, "ALPHA",   "체크포인트 1"),
    ( 0.400,  1.5000, None,      "상단 회랑 복귀"),
    ( 1.900,  1.4850, None,      "상단 회랑 중앙 / 우측 코너 진입"),
    ( 2.245,  0.9200, None,      "우측 회랑 중앙 x=2.245"),
    ( 2.245,  0.3000, None,      "우측 회랑 중앙"),
    ( 1.700,  0.1900, None,      "십자 가로 회랑 y=0.18 진입"),
    ( 0.560,  0.1800, None,      "중앙 십자 교차로"),
    ( 0.150,  0.1850, None,      "회랑 중앙 핀 — 없으면 객체6(미사일) 쪽으로 부푼다"),
    (-0.260,  0.2000, None,      "BRAVO 진입 — SEC6 북서 모서리를 서쪽으로 우회"),
    (-0.390, -0.1300, "BRAVO",   "체크포인트 2 (헤어핀 정점)"),
    (-0.670,  0.1500, None,      "BRAVO 이탈"),
    (-1.030,  0.4175, None,      "게이트 중앙: 포트홀1 북단 0.26 / 배리어1 남단 0.575"),
    (-1.300,  0.4000, None,      "배리어1 서단(-1.16) 통과 핀"),
    (-1.750,  0.3600, None,      "SEC7 객체군 북측"),
    (-2.160,  0.0800, None,      "좌측 회랑 진입"),
    (-2.245, -0.7000, None,      "좌측 회랑 중앙 x=-2.245"),
    (-2.245, -1.3000, None,      "좌측 회랑 중앙 / 좌하단 코너"),
    (-1.550, -1.6400, "CHARLIE", "체크포인트 3"),
    (-1.200, -1.6720, None,      "포트홀2 회피 진입 — 남측으로 비킨다"),
    (-0.610, -1.6720, None,      "포트홀2 정남 통과 (직선 유지로 차체 회전 최소화)"),
    ( 0.010, -1.5750, None,      "회랑 복귀 시작"),
    ( 0.750, -1.5250, None,      "하단 회랑 중앙 y=-1.525"),
    ( 1.350, -1.6252, None,      "FINISH 활강 (포물선: 종점에서 접선이 수평)"),
    ( 1.900, -1.6790, None,      "FINISH 활강"),
    ( 2.150, -1.6800, None,      "FINISH 진입 — 여기서부터 벽과 평행"),
    ( 2.230, -1.6800, "FINISH",  "결승선"),
]

# 회랑(도로) 중앙선 — 20_markings.py 의 블록 경계선에서 산출한 값
# (name, 축, 중앙값, 진행축 범위, 반폭)
CORRIDORS = [
    ("TOP",       'y',  1.490, (-2.245, 2.245), 0.220),
    ("BOTTOM",    'y', -1.525, (-2.245, 2.245), 0.185),
    ("LEFT",      'x', -2.245, (-1.525, 1.490), 0.165),
    ("RIGHT",     'x',  2.245, (-1.525, 1.490), 0.165),
    ("CROSS_H",   'y',  0.180, (-2.080, 2.080), 0.130),
    ("CROSS_V_N", 'x',  0.560, (0.310, 1.270), 0.120),
    ("CROSS_V_S", 'x',  0.560, (-1.340, 0.050), 0.140),
]


# ==================================================================
# GEOMETRY CORE BEGIN — bpy 비의존. 오프라인에서 그대로 재현/검증 가능하다.
# ==================================================================
def _sub(a, b): return (a[0] - b[0], a[1] - b[1])
def _add(a, b): return (a[0] + b[0], a[1] + b[1])
def _mul(a, s): return (a[0] * s, a[1] * s)
def _len(a): return math.hypot(a[0], a[1])


def _unit(a):
    l = _len(a)
    return (a[0] / l, a[1] / l) if l > 1e-12 else (0.0, 0.0)


def circumcircle(a, b, c):
    """세 점의 외접원 (center, R). 거의 일직선이면 (None, 큰 값)."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None, 1e9
    a2 = ax * ax + ay * ay
    b2 = bx * bx + by * by
    c2 = cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    return (ux, uy), math.hypot(ax - ux, ay - uy)


def tangents_of(pts):
    """제어점별 접선 방향. 세 점의 외접원 접선 = 원호를 정확히 재현한다."""
    n = len(pts)
    out = []
    for i in range(n):
        if i == 0:
            out.append(_unit(_sub(pts[1], pts[0])))
            continue
        if i == n - 1:
            out.append(_unit(_sub(pts[-1], pts[-2])))
            continue
        C, r = circumcircle(pts[i - 1], pts[i], pts[i + 1])
        ref = _unit(_sub(pts[i + 1], pts[i - 1]))
        if C is None or r > 50.0:
            out.append(ref)
            continue
        rad = _sub(pts[i], C)
        t = _unit((-rad[1], rad[0]))            # 반경에 수직 = 원의 접선
        if t[0] * ref[0] + t[1] * ref[1] < 0.0:
            t = (-t[0], -t[1])                  # 진행 방향으로 정렬
        out.append(t)
    return out


def arc_handles(pts, tan, cap=0.55):
    """원호 근사 핸들 길이.  h = |c| / (3 cos^2(a/2)),  a = 접선과 코드의 각.

    a -> 0 이면 |c|/3 (직선 구간의 표준값)으로 수렴하고, 코너에서는 자연스럽게
    길어져 원호에 가까워진다.
    """
    n = len(pts)
    hl = [0.0] * n
    hr = [0.0] * n
    for i in range(n - 1):
        c = _sub(pts[i + 1], pts[i])
        L = _len(c)
        u = _unit(c)
        ca = max(-1.0, min(1.0, tan[i][0] * u[0] + tan[i][1] * u[1]))
        cb = max(-1.0, min(1.0, tan[i + 1][0] * u[0] + tan[i + 1][1] * u[1]))
        a = min(math.acos(ca), 1.4)
        b = min(math.acos(cb), 1.4)
        hr[i] = min(L / (3.0 * math.cos(a * 0.5) ** 2), cap * L)
        hl[i + 1] = min(L / (3.0 * math.cos(b * 0.5) ** 2), cap * L)
    hl[0] = hr[0]
    hr[n - 1] = hl[n - 1]
    return hl, hr


def handle_points(pts, tan, hl, hr):
    HL = [_sub(pts[i], _mul(tan[i], hl[i])) for i in range(len(pts))]
    HR = [_add(pts[i], _mul(tan[i], hr[i])) for i in range(len(pts))]
    return HL, HR


def _bez(p0, p1, p2, p3, t):
    m = 1.0 - t
    a, b, c, d = m * m * m, 3 * m * m * t, 3 * m * t * t, t * t * t
    return (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
            a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])


def _bez_d1(p0, p1, p2, p3, t):
    m = 1.0 - t
    a, b, c = 3 * m * m, 6 * m * t, 3 * t * t
    return (a * (p1[0] - p0[0]) + b * (p2[0] - p1[0]) + c * (p3[0] - p2[0]),
            a * (p1[1] - p0[1]) + b * (p2[1] - p1[1]) + c * (p3[1] - p2[1]))


def _bez_d2(p0, p1, p2, p3, t):
    m = 1.0 - t
    a, b = 6 * m, 6 * t
    return (a * (p2[0] - 2 * p1[0] + p0[0]) + b * (p3[0] - 2 * p2[0] + p1[0]),
            a * (p2[1] - 2 * p1[1] + p0[1]) + b * (p3[1] - 2 * p2[1] + p1[1]))


def sample_curve(pts, HL, HR, m):
    """[(x, y, |kappa|, seg, t, heading, kappa_signed), ...]"""
    out = []
    n = len(pts)
    for i in range(n - 1):
        p0, p1, p2, p3 = pts[i], HR[i], HL[i + 1], pts[i + 1]
        last = m + (1 if i == n - 2 else 0)
        for k in range(last):
            t = k / float(m)
            p = _bez(p0, p1, p2, p3, t)
            d1 = _bez_d1(p0, p1, p2, p3, t)
            d2 = _bez_d2(p0, p1, p2, p3, t)
            sp = _len(d1)
            if sp > 1e-9:
                kap = (d1[0] * d2[1] - d1[1] * d2[0]) / (sp ** 3)
            else:
                kap = 0.0
            out.append((p[0], p[1], abs(kap), i, t,
                        math.atan2(d1[1], d1[0]), kap))
    return out


def dist_to_rect(p, cx, cy, hx, hy, yaw=0.0):
    dx, dy = p[0] - cx, p[1] - cy
    if yaw:
        c, s = math.cos(-yaw), math.sin(-yaw)
        dx, dy = dx * c - dy * s, dx * s + dy * c
    return math.hypot(max(abs(dx) - hx, 0.0), max(abs(dy) - hy, 0.0))


def build_obstacles(spec, half_w, margin, pothole_margin):
    """(name, fn(point)->거리, 필요거리) 목록. 중심선 검사용이라 half_w 포함."""
    obs = []
    for ph in spec["potholes"]:
        q = tuple(ph["pos"])
        obs.append(("pothole_%d" % ph["id"],
                    (lambda qq: lambda p: math.hypot(p[0] - qq[0], p[1] - qq[1]))(q),
                    ph["r"] + half_w + pothole_margin))
    for sn in sorted(spec["sectors"], key=lambda k: int(k)):
        sc = spec["sectors"][sn]
        c, h = tuple(sc["pos"]), tuple(sc["half_extent"])
        obs.append(("sector_%s" % sn,
                    (lambda cc, hh: lambda p: dist_to_rect(p, cc[0], cc[1], hh[0], hh[1]))(c, h),
                    half_w + margin))
    for ob in spec["objects"]:
        q = tuple(ob["pos"])
        r = spec["object_kinds"][ob["kind"]]["r"]
        obs.append(("obj_%02d_%s" % (ob["id"], ob["kind"]),
                    (lambda qq: lambda p: math.hypot(p[0] - qq[0], p[1] - qq[1]))(q),
                    r + half_w + margin))
    for br in spec["barriers"]:
        c, s, y = tuple(br["pos"]), tuple(br["size"]), float(br["yaw"])
        obs.append(("barrier_%d" % br["id"],
                    (lambda cc, ss, yy: lambda p: dist_to_rect(
                        p, cc[0], cc[1], ss[0] * 0.5, ss[1] * 0.5, yy))(c, s, y),
                    half_w + margin))
    return obs


def worst_clearance(samples, obstacles):
    """장애물별 최악 지점. {name: (거리, 필요, seg, t, x, y)}"""
    worst = {}
    for x, y, kap, seg, t, th, ks in samples:
        p = (x, y)
        for name, fn, req in obstacles:
            d = fn(p)
            cur = worst.get(name)
            if cur is None or d < cur[0]:
                worst[name] = (d, req, seg, t, x, y)
    return worst


def repair_handles(pts, tan, hl, hr, obstacles, rounds=40, m=SAMPLES_PER_SEG):
    """클리어런스 위반이 사라질 때까지 해당 구간 핸들만 국소적으로 줄인다.

    경로를 통째로 다시 그리지 않는다 — 그러면 체크포인트 통과가 깨진다.
    """
    for it in range(rounds):
        HL, HR = handle_points(pts, tan, hl, hr)
        S = sample_curve(pts, HL, HR, m)
        worst = worst_clearance(S, obstacles)
        viol = [(n,) + v for n, v in worst.items() if v[0] < v[1]]
        if not viol:
            return hl, hr, it
        for name, d, req, seg, t, x, y in viol:
            wa = 3.0 * (1 - t) ** 2 * t          # HR[seg] 기여도
            wb = 3.0 * (1 - t) * t * t           # HL[seg+1] 기여도
            if wa >= wb:
                hr[seg] = max(0.02, hr[seg] * 0.90)
                hl[seg + 1] = max(0.02, hl[seg + 1] * 0.95)
            else:
                hl[seg + 1] = max(0.02, hl[seg + 1] * 0.90)
                hr[seg] = max(0.02, hr[seg] * 0.95)
    return hl, hr, rounds


def steer_of(kappa_signed, wheelbase, steer_max):
    """자전거 모델 조향각. 헤어핀에서는 포화한다 (그래서 clamp)."""
    d = math.atan(wheelbase * abs(kappa_signed))
    return math.copysign(min(d, steer_max), kappa_signed)


def silhouette_geom(spec):
    """차체 실루엣 부품 좌표 (70_vehicle.py 지오메트리 기준, 로컬 XY).

    헐은 반폭 0.045, 바퀴만 0.065 까지 나간다. 0.20x0.13 사각형으로 잡으면
    앞뒤 모서리를 과대평가해 통과 가능한 코너를 막는다.
    반환: (헐 4모서리, 뒷바퀴 4모서리, 앞바퀴 허브 기준 로컬 4모서리, 허브 좌표)
    """
    v = spec.get("vehicle", {})
    L = float(v.get("size", [0.20, 0.13, 0.09])[0])
    hw = float(v.get("half_w", 0.065))
    wr = float(v.get("wheel_r", 0.022))
    ww = float(v.get("wheel_w", 0.018))
    hx = L * 0.5 - 0.002                 # 헐 앞뒤 끝
    hy = hw - ww - 0.002                 # 헐 반폭 (바퀴 안쪽)
    hub_x = 0.062                        # 휠베이스/2
    hub_y = hw - ww * 0.5                # 바퀴 중심 Y (0.056)
    dx = wr + 0.002
    dy = ww * 0.5
    hull = [(hx, hy), (hx, -hy), (-hx, hy), (-hx, -hy)]
    rear = [(-hub_x + a, sy * hub_y + b)
            for sy in (1.0, -1.0) for a in (dx, -dx) for b in (dy, -dy)]
    front_local = [(a, b) for a in (dx, -dx) for b in (dy, -dy)]
    return hull, rear, front_local, (hub_x, hub_y)


def silhouette_points(spec, steer=0.0, _cache={}):
    """조향각을 반영한 실루엣 점 목록 (로컬 XY)."""
    key = id(spec)
    g = _cache.get(key)
    if g is None:
        g = _cache[key] = silhouette_geom(spec)
    hull, rear, front_local, (hx, hy) = g
    c, s = math.cos(steer), math.sin(steer)
    pts = list(hull) + list(rear)
    for sy in (1.0, -1.0):
        for a, b in front_local:
            pts.append((hx + a * c - b * s, sy * hy + a * s + b * c))
    return pts


def sweep_points(samples, spec, wheelbase, steer_max):
    """샘플별 (월드 실루엣 점 목록) 생성기. 조향각은 국소 곡률에서 만든다."""
    for x, y, kap, seg, t, th, ks in samples:
        d = steer_of(ks, wheelbase, steer_max)
        sil = silhouette_points(spec, d)
        c, s = math.cos(th), math.sin(th)
        yield (x, y, seg, t, d,
               [(x + lx * c - ly * s, y + lx * s + ly * c) for lx, ly in sil])


def arena_clamp(pts, tags, obstacles, spec, bounds, inset,
                wheelbase=0.124, steer_max=0.0, rounds=6):
    """차체 실루엣이 아레나 벽을 침범하면 태그 없는 제어점만 최소량 안쪽으로.

    측량사의 drive_envelope 는 차폭만 뺀 값이라 차체가 '회전'했을 때
    모서리가 벽을 스치는 것을 못 잡는다. 그 차이만 여기서 메운다.
    태그 점(START/ALPHA/BRAVO/CHARLIE/FINISH)은 절대 움직이지 않는다.
    """
    pts = list(pts)
    moved = {}
    tan = tangents_of(pts)
    hl, hr = arc_handles(pts, tan)
    hl, hr, _ = repair_handles(pts, tan, list(hl), list(hr), obstacles)
    for outer in range(rounds):
        HL, HR = handle_points(pts, tan, hl, hr)
        S = sample_curve(pts, HL, HR, 90)
        push = [[0.0, 0.0] for _ in pts]
        bad = 0
        for x, y, seg, t, dsteer, wpts in sweep_points(S, spec, wheelbase, steer_max):
            for px, py in wpts:
                for ax, val, lo, hi in ((0, px, bounds["x"][0], bounds["x"][1]),
                                        (1, py, bounds["y"][0], bounds["y"][1])):
                    over = max(lo + inset - val, val - (hi - inset))
                    if over <= 0.0:
                        continue
                    bad += 1
                    sgn = 1.0 if val < 0.0 else -1.0
                    wa = (1 - t) ** 3 + 3 * (1 - t) ** 2 * t
                    wb = 3 * (1 - t) * t * t + t ** 3
                    for idx, w in ((seg, wa), (seg + 1, wb)):
                        if tags[idx]:
                            continue
                        dd = sgn * over * w * 1.15
                        if abs(dd) > abs(push[idx][ax]):
                            push[idx][ax] = dd
        if not bad:
            break
        for i in range(len(pts)):
            if push[i][0] or push[i][1]:
                pts[i] = (pts[i][0] + push[i][0], pts[i][1] + push[i][1])
                acc = moved.setdefault(i, [0.0, 0.0])
                acc[0] += push[i][0]
                acc[1] += push[i][1]
        tan = tangents_of(pts)
        hl, hr = arc_handles(pts, tan)
        hl, hr, _ = repair_handles(pts, tan, list(hl), list(hr), obstacles)
    return pts, tan, hl, hr, moved


def raw_obstacles(spec):
    """실루엣 스윕용 — 장애물 반경만 빼고 차폭은 빼지 않는다."""
    obs = []
    for ph in spec["potholes"]:
        q = tuple(ph["pos"])
        obs.append(("pothole_%d" % ph["id"],
                    (lambda qq: lambda p: math.hypot(p[0] - qq[0], p[1] - qq[1]))(q), ph["r"]))
    for sn in sorted(spec["sectors"], key=lambda k: int(k)):
        sc = spec["sectors"][sn]
        c, h = tuple(sc["pos"]), tuple(sc["half_extent"])
        obs.append(("sector_%s" % sn,
                    (lambda cc, hh: lambda p: dist_to_rect(p, cc[0], cc[1], hh[0], hh[1]))(c, h), 0.0))
    for ob in spec["objects"]:
        q = tuple(ob["pos"])
        obs.append(("obj_%02d_%s" % (ob["id"], ob["kind"]),
                    (lambda qq: lambda p: math.hypot(p[0] - qq[0], p[1] - qq[1]))(q),
                    spec["object_kinds"][ob["kind"]]["r"]))
    for br in spec["barriers"]:
        c, s, y = tuple(br["pos"]), tuple(br["size"]), float(br["yaw"])
        obs.append(("barrier_%d" % br["id"],
                    (lambda cc, ss, yy: lambda p: dist_to_rect(
                        p, cc[0], cc[1], ss[0] * 0.5, ss[1] * 0.5, yy))(c, s, y), 0.0))
    return obs


def swept_clearance(samples, spec, bounds, wheelbase=0.124, steer_max=0.0):
    """실제 차체 실루엣(조향 포함) 기준 최소 클리어런스.

    반환: (worst{name:(d, x, y, steer_deg)}, wall_min, wall_at, per_sample_wall)
    """
    obs = raw_obstacles(spec)
    worst = {}
    wall = 9.0
    wall_at = None
    wall_series = []
    for x, y, seg, t, dsteer, wpts in sweep_points(samples, spec, wheelbase, steer_max):
        wmin = 9.0
        for px, py in wpts:
            for name, fn, r in obs:
                d = fn((px, py)) - r
                cur = worst.get(name)
                if cur is None or d < cur[0]:
                    worst[name] = (d, x, y, math.degrees(dsteer))
            w = min(px - bounds["x"][0], bounds["x"][1] - px,
                    py - bounds["y"][0], bounds["y"][1] - py)
            if w < wmin:
                wmin = w
        wall_series.append(wmin)
        if wmin < wall:
            wall = wmin
            wall_at = (round(x, 4), round(y, 4))
    return worst, wall, wall_at, wall_series


def corridor_report(samples, corridors):
    """샘플이 속한 회랑을 찾아 중앙선 이탈을 집계한다."""
    acc = {}
    for x, y, kap, seg, t, th, ks in samples:
        best = None
        for nm, ax, c, rng, half in corridors:
            u = y if ax == 'x' else x                 # 회랑 진행축
            if not (rng[0] - 0.05 <= u <= rng[1] + 0.05):
                continue
            d = abs((x if ax == 'x' else y) - c)
            if d > half:
                continue
            if best is None or d < best[1]:
                best = (nm, d)
        if best:
            a = acc.setdefault(best[0], [0.0, 0, 0.0])
            a[0] += best[1]
            a[1] += 1
            a[2] = max(a[2], best[1])
    return {k: {"mean_offset_m": round(v[0] / v[1], 4),
                "max_offset_m": round(v[2], 4),
                "samples": v[1]} for k, v in acc.items()}


def hazard_arclen(samples, arclen, hazards):
    """하자드별 경로 최근접 호장 위치와 중심선 거리."""
    out = {}
    for name, q, r in hazards:
        k = min(range(len(samples)),
                key=lambda i: (samples[i][0] - q[0]) ** 2 + (samples[i][1] - q[1]) ** 2)
        out[name] = (arclen[k],
                     math.hypot(samples[k][0] - q[0], samples[k][1] - q[1]), r)
    return out


def build_speed_profile(samples, arclen, total_len, cp_arc, haz_arc, drive_seconds):
    """물리 기반 속도 프로파일 -> 프레임별 진행 거리.

    감속캡은 여러 딥을 곱하지 않고 min 으로 합친다. 곱하면 체크포인트와
    하자드가 가까울 때 캡이 0.3 이하로 내려가 차가 기어가는 것처럼 보인다.
    반환: (frame_s, v_grid, ds, stats)
    """
    ns = GRID_N
    ds = total_len / ns

    def at(target):
        lo, hi = 0, len(arclen) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if arclen[mid] <= target:
                lo = mid
            else:
                hi = mid
        f = (target - arclen[lo]) / max(arclen[hi] - arclen[lo], 1e-12)
        return samples[lo][2] + (samples[hi][2] - samples[lo][2]) * f

    kap = [at(i * ds) for i in range(ns + 1)]
    # 코너 '진입 전'부터 느려져야 자연스럽다 -> max 필터
    sm = []
    for i in range(len(kap)):
        a = max(0, i - KAP_WIN)
        b = min(len(kap), i + KAP_WIN + 1)
        sm.append(max(kap[a:b]))
    kap = sm

    v = []
    caps = []
    for i in range(ns + 1):
        s_here = i * ds
        cap = 1.0
        for tg in ("ALPHA", "BRAVO", "CHARLIE"):
            if tg not in cp_arc:
                continue
            d = (s_here - cp_arc[tg]) / CP_SIG
            cap = min(cap, 1.0 - CP_DIP * math.exp(-d * d))
        for nm, s_h in haz_arc.items():
            d = s_here - s_h
            sig = HAZ_SIG_B if d < 0.0 else HAZ_SIG_A
            cap = min(cap, 1.0 - HAZ_DIP * math.exp(-(d / sig) ** 2))
        caps.append(cap)
        lat = math.sqrt(A_LAT / kap[i]) if kap[i] > 1e-6 else V_MAX
        v.append(min(V_MAX * cap, lat))
    v[0] = 0.0
    v[ns] = 0.0
    for i in range(ns):                                   # 가속 한계
        v[i + 1] = min(v[i + 1], math.sqrt(v[i] ** 2 + 2.0 * A_ACC * ds))
    for i in range(ns - 1, -1, -1):                       # 감속 한계
        v[i] = min(v[i], math.sqrt(v[i + 1] ** 2 + 2.0 * A_DEC * ds))

    tt = [0.0]
    for i in range(ns):
        tt.append(tt[-1] + 2.0 * ds / max(v[i] + v[i + 1], 1e-6))
    lam = drive_seconds / tt[-1]
    tt = [x * lam for x in tt]
    v = [x / lam for x in v]

    nframes = DRIVE_F1 - DRIVE_F0
    frame_s = []
    j = 0
    for k in range(nframes + 1):
        t = drive_seconds * k / float(nframes)
        while j < ns and tt[j + 1] < t:
            j += 1
        if j >= ns:
            frame_s.append(total_len)
            continue
        a, b = tt[j], tt[j + 1]
        fr = (t - a) / max(b - a, 1e-9)
        frame_s.append(min(total_len, (j + fr) * ds))
    frame_s[-1] = total_len
    stats = {"time_scale": lam,
             "v_max": max(v), "v_mean": total_len / drive_seconds,
             "v_min_moving": min(x for x in v[1:-1]),
             "cap_min": min(caps)}
    return frame_s, v, ds, stats
# ==================================================================
# GEOMETRY CORE END
# ==================================================================


# ---------------------------------------------------------------- F커브 유틸
def _fcurves_of(id_block):
    """액션의 F커브 컬렉션. 4.4 슬롯(layer/strip/channelbag) 액션도 처리한다."""
    ad = getattr(id_block, "animation_data", None)
    if ad is None or ad.action is None:
        return None
    act = ad.action
    fcs = None
    try:
        fcs = act.fcurves
        if len(fcs) > 0:
            return fcs
    except Exception:
        fcs = None
    try:                                   # Blender 4.4+ 슬롯 액션
        slot = getattr(ad, "action_slot", None)
        for layer in act.layers:
            for strip in layer.strips:
                bag = None
                if slot is not None and hasattr(strip, "channelbag"):
                    try:
                        bag = strip.channelbag(slot)
                    except Exception:
                        bag = None
                if bag is None:
                    bags = getattr(strip, "channelbags", None)
                    bag = bags[0] if bags else None
                if bag is not None and len(bag.fcurves) > 0:
                    return bag.fcurves
    except Exception:
        pass
    return fcs


def _find_fcurve(id_block, data_path, index):
    fcs = _fcurves_of(id_block)
    if fcs is None:
        return None
    for fc in fcs:
        if fc.data_path == data_path and (index is None or fc.array_index == index):
            return fc
    return None


def _set_prop(owner, data_path, index, value):
    if index is None:
        setattr(owner, data_path, value)
    else:
        getattr(owner, data_path)[index] = value


def bake_channel(owner, data_path, index, frames, values,
                 interp='LINEAR', handle='AUTO_CLAMPED'):
    """프레임/값 배열을 F커브에 한 번에 굽는다.

    keyframe_insert 를 프레임 수만큼 호출하면 700+ 프레임에서 느리고,
    호출 사이에 애니메이션이 프로퍼티를 되덮어쓸 여지가 있다.
    첫 키만 keyframe_insert 로 만들어 액션/슬롯 생성을 블렌더에 맡기고,
    나머지는 keyframe_points 에 직접 채운다.
    """
    assert len(frames) == len(values) and len(frames) > 0
    _set_prop(owner, data_path, index, float(values[0]))
    if index is None:
        owner.keyframe_insert(data_path, frame=int(frames[0]))
    else:
        owner.keyframe_insert(data_path, index=index, frame=int(frames[0]))
    fc = _find_fcurve(owner, data_path, index)
    if fc is None:                                   # 폴백 (구조가 다른 버전)
        for f, v in zip(frames, values):
            _set_prop(owner, data_path, index, float(v))
            if index is None:
                owner.keyframe_insert(data_path, frame=int(f))
            else:
                owner.keyframe_insert(data_path, index=index, frame=int(f))
        return _find_fcurve(owner, data_path, index)
    kps = fc.keyframe_points
    if len(kps) != 1:                                # 이미 키가 있으면 안전 경로
        for f, v in zip(frames[1:], values[1:]):
            _set_prop(owner, data_path, index, float(v))
            if index is None:
                owner.keyframe_insert(data_path, frame=int(f))
            else:
                owner.keyframe_insert(data_path, index=index, frame=int(f))
    else:
        if len(frames) > 1:
            kps.add(len(frames) - 1)
        for i in range(len(frames)):
            kps[i].co = (float(frames[i]), float(values[i]))
    for kp in kps:
        kp.interpolation = interp
        kp.handle_left_type = handle
        kp.handle_right_type = handle
    fc.update()
    return fc


def add_noise_modifier(fc, strength, scale, phase=0.0,
                       frame_range=None, blend=(0.0, 0.0)):
    """F커브 노이즈 모디파이어. 키프레임 수백 개를 찍는 것보다 가볍다."""
    if fc is None:
        return None
    nm = fc.modifiers.new('NOISE')
    nm.strength = float(strength)
    nm.scale = float(scale)
    nm.phase = float(phase)
    try:
        nm.blend_type = 'ADD'          # 기존 키 값 위에 더한다
    except Exception:
        pass
    try:
        nm.depth = 0
    except Exception:
        pass
    if frame_range is not None:
        nm.use_restricted_range = True
        nm.frame_start = float(frame_range[0])
        nm.frame_end = float(frame_range[1])
        nm.blend_in = float(blend[0])
        nm.blend_out = float(blend[1])
    return nm


def clear_anim(obj):
    if obj is not None and obj.animation_data is not None:
        obj.animation_data_clear()


# ================================================================== 빌드 시작
purge("PATH_")
COL = link_collection("06_Vehicle")

scene = bpy.context.scene
scene.render.fps = FPS
scene.render.fps_base = 1.0
scene.frame_start = 1
scene.frame_end = TOTAL_FRAMES

VS = SPEC.get("vehicle", {})
HALF_W = float(VS.get("half_w", 0.065))
BOUNDS = SPEC["arena"]["bounds"]

# ---------------------------------------------------------------- 1. 경로 기하
PTS0 = [(float(p[0]), float(p[1])) for p in PATH_PTS]
TAGS = [p[2] for p in PATH_PTS]
NOTES = [p[3] for p in PATH_PTS]
assert len(PTS0) == len(TAGS) >= 4, "path 제어점이 부족하다"

# 태그 점은 스펙 좌표 그대로여야 한다. 어긋나면 경로를 손댈 때 체크포인트를
# 슬쩍 옮긴 것이므로 여기서 즉시 멈춘다.
TAG_SRC = {"START": tuple(SPEC["start"]["pos"]), "FINISH": tuple(SPEC["finish"]["pos"])}
for _nm in ("ALPHA", "BRAVO", "CHARLIE"):
    TAG_SRC[_nm] = tuple(SPEC["checkpoints"][_nm]["pos"])
for i, tg in enumerate(TAGS):
    if not tg:
        continue
    q = TAG_SRC[tg]
    assert abs(PTS0[i][0] - q[0]) < 1e-9 and abs(PTS0[i][1] - q[1]) < 1e-9, \
        "%s 제어점이 스펙과 다르다: %s vs %s (태그 점은 절대 움직이지 않는다)" % (tg, PTS0[i], q)
assert sorted(t for t in TAGS if t) == sorted(TAG_SRC), "태그 점 누락/중복"

OBSTACLES = build_obstacles(SPEC, HALF_W, CLEAR_MARGIN, POTHOLE_MARGIN)
WHEELBASE_G = float(SPEC.get("vehicle", {}).get("wheelbase", 0.124))

PTS, TAN, HLEN, HRLEN, MOVED = arena_clamp(
    PTS0, TAGS, OBSTACLES, SPEC, BOUNDS, WALL_INSET,
    wheelbase=WHEELBASE_G, steer_max=STEER_MAX)
HL, HR = handle_points(PTS, TAN, HLEN, HRLEN)

SAMP = sample_curve(PTS, HL, HR, SAMPLES_FINAL)
ARC = [0.0]
for i in range(1, len(SAMP)):
    ARC.append(ARC[-1] + math.hypot(SAMP[i][0] - SAMP[i - 1][0],
                                    SAMP[i][1] - SAMP[i - 1][1]))
PATH_LEN = ARC[-1]
KAP_MAX = max(s[2] for s in SAMP)
R_MIN_CURVE = 1.0 / KAP_MAX if KAP_MAX > 1e-9 else 1e9

# 태그 점의 호장 위치 (속도 곡선의 감속 지점)
CP_ARC = {}
CP_XY = {}
for i, tg in enumerate(TAGS):
    if not tg:
        continue
    k = min(range(len(SAMP)),
            key=lambda j: (SAMP[j][0] - PTS[i][0]) ** 2 + (SAMP[j][1] - PTS[i][1]) ** 2)
    CP_ARC[tg] = ARC[k]
    CP_XY[tg] = PTS[i]

# 하자드(포트홀 2 + 배리어 2) 최근접 호장 — 속도 딥과 회피 창의 기준점
HAZARDS = []
for ph in SPEC["potholes"]:
    HAZARDS.append(("pothole_%d" % ph["id"], tuple(ph["pos"]), float(ph["r"])))
for br in SPEC["barriers"]:
    HAZARDS.append(("barrier_%d" % br["id"], tuple(br["pos"]),
                    max(br["size"][0], br["size"][1]) * 0.5))
HAZ_INFO = hazard_arclen(SAMP, ARC, HAZARDS)
# FINISH 정지 감속과 겹치는 하자드는 딥을 따로 주지 않는다 (이중 감속 방지)
HAZ_ARC = {k: v[0] for k, v in HAZ_INFO.items() if v[0] < PATH_LEN - 0.45}

# 제어점별 호장 (카메라 컷 구간 산출용)
CTRL_ARC = []
for i in range(len(PTS)):
    k = min(range(len(SAMP)),
            key=lambda j: (SAMP[j][0] - PTS[i][0]) ** 2 + (SAMP[j][1] - PTS[i][1]) ** 2)
    CTRL_ARC.append(ARC[k])

# ---------------------------------------------------------------- 2. 경로 검산
CLEAR = worst_clearance(SAMP, OBSTACLES)
CLEAR_VIOL = [(n, v[0], v[1]) for n, v in CLEAR.items() if v[0] < v[1]]
SWEPT, WALL_MIN, WALL_AT, WALL_SERIES = swept_clearance(
    SAMP, SPEC, BOUNDS, wheelbase=WHEELBASE_G, steer_max=STEER_MAX)
CORRIDOR_QA = corridor_report(SAMP, CORRIDORS)

# 벽에 붙어 가는 '거리' — 최소값만 보면 개선 여부가 안 보인다
WALL_EXPOSURE = 0.0
for i in range(1, len(SAMP)):
    if WALL_SERIES[i] < 0.03:
        WALL_EXPOSURE += ARC[i] - ARC[i - 1]

CP_ON_PATH = {}
for name in ("ALPHA", "BRAVO", "CHARLIE"):
    q = SPEC["checkpoints"][name]["pos"]
    CP_ON_PATH[name] = min(math.hypot(s[0] - q[0], s[1] - q[1]) for s in SAMP)

print("[80_motion] --- 경로 기하 ---")
print("  제어점 %d개 / 길이 %.4f m / 전역 최소 곡률반경 %.4f m"
      % (len(PTS), PATH_LEN, R_MIN_CURVE))
if MOVED:
    print("  아레나 벽 클램프(태그 없는 점만, 차체 실루엣 기준): %s"
          % ", ".join("P%02d(%+.4f,%+.4f)" % (i, d[0], d[1]) for i, d in sorted(MOVED.items())))
else:
    print("  아레나 벽 클램프: 없음")
for name in ("ALPHA", "BRAVO", "CHARLIE"):
    print("  체크포인트 %-8s 커브 최소거리 %.5f m" % (name, CP_ON_PATH[name]))
print("  중심선 클리어런스 여유 하위 5 (거리 - 필요치):")
for n, (d, req, seg, t, x, y) in sorted(CLEAR.items(), key=lambda kv: kv[1][0] - kv[1][1])[:5]:
    print("    %-18s %.4f - %.4f = %+.4f  @(%.3f, %.3f)" % (n, d, req, d - req, x, y))
print("  차체 실루엣 스윕 클리어런스 하위 6 (조향 %.0f° 반영):" % math.degrees(STEER_MAX))
for n, (d, x, y, sd) in sorted(SWEPT.items(), key=lambda kv: kv[1][0])[:6]:
    print("    %-18s %.4f m  @(%.3f, %.3f) 조향 %+.1f°" % (n, d, x, y, sd))
print("    아레나 벽까지        %.4f m  @%s | 0.03 m 미만 구간 길이 %.3f m"
      % (WALL_MIN, WALL_AT, WALL_EXPOSURE))
print("  회랑 중앙 이탈 (평균 / 최대 / 샘플):")
for k in sorted(CORRIDOR_QA):
    v = CORRIDOR_QA[k]
    print("    %-10s %.4f / %.4f / %d"
          % (k, v["mean_offset_m"], v["max_offset_m"], v["samples"]))

assert not CLEAR_VIOL, "클리어런스 위반: %s" % CLEAR_VIOL
for name in ("ALPHA", "BRAVO", "CHARLIE"):
    assert CP_ON_PATH[name] <= CP_TOL, \
        "체크포인트 %s 가 경로에서 %.4f m 떨어져 있다" % (name, CP_ON_PATH[name])
for ph in SPEC["potholes"]:
    need = ph["r"] + HALF_W + POTHOLE_MARGIN
    got = CLEAR["pothole_%d" % ph["id"]][0]
    assert got >= need, "포트홀 %d 회피 실패 (%.4f < %.4f)" % (ph["id"], got, need)
assert WALL_MIN >= 0.0, "차체가 아레나 벽을 침범한다 (%.4f)" % WALL_MIN

R_MIN_NOTE = None
if R_MIN_CURVE < R_MIN_TARGET:
    # 기하학적 상한이라 핸들 조정으로는 못 넘는다. 경고로 남기고 진행한다.
    R_MIN_NOTE = ("최소 곡률반경 %.4f m < 목표 %.2f m — BRAVO 헤어핀. "
                  "BRAVO(-0.39,-0.13) 를 지나며 SEC6 모서리(-0.163,-0.005) 를 "
                  "0.085 m 띄우는 원의 최대 반경이 0.143 m 라 상한이 기하로 정해진다. "
                  "게다가 이 코너는 SEC6 클리어런스와 반경이 정면 충돌한다"
                  "(진입점 x=-0.15 → SEC6 0.019/R 0.124, x=-0.26 → SEC6 0.070/R 0.087). "
                  "19 mm 는 렌더에서 '긁고 지나감'으로 보이므로 건물 회피를 우선했고, "
                  "이 코너 속도를 크게 낮춰 보완했다."
                  % (R_MIN_CURVE, R_MIN_TARGET))
    print("  [경고] " + R_MIN_NOTE)

WALL_NOTE = ("아레나 벽 최소 여유 %.4f m 는 FINISH 태그가 정하는 상한이다. "
             "FINISH(2.23,-1.68) → 노면 경계 y=-1.75 까지 0.070, 차체 반폭 0.065 → 0.005. "
             "FINISH 를 옮기지 않는 한 못 올린다. 대신 벽에 붙어 가는 거리를 줄였다 "
             "(0.03 m 미만 구간 %.3f m)." % (WALL_MIN, WALL_EXPOSURE))
if WALL_MIN < 0.010:
    print("  [경고] " + WALL_NOTE)

# ---------------------------------------------------------------- 3. 커브 생성
cu = bpy.data.curves.new("PATH_Main_crv", 'CURVE')
cu.dimensions = '3D'
cu.resolution_u = CURVE_RES_U
cu.twist_mode = 'MINIMUM'
sp = cu.splines.new('BEZIER')
sp.bezier_points.add(len(PTS) - 1)
for i, bp in enumerate(sp.bezier_points):
    # 타입을 먼저 FREE 로 바꾼 뒤 좌표를 넣는다. AUTO/ALIGNED 상태에서 co 를
    # 대입하면 블렌더가 핸들을 다시 계산해 위 검산이 무의미해진다.
    bp.handle_left_type = 'FREE'
    bp.handle_right_type = 'FREE'
    bp.co = (PTS[i][0], PTS[i][1], 0.0)
    bp.handle_left = (HL[i][0], HL[i][1], 0.0)
    bp.handle_right = (HR[i][0], HR[i][1], 0.0)
    bp.tilt = 0.0                # tilt 가 있으면 차가 기운다
    bp.radius = 1.0
sp.use_cyclic_u = False          # START -> FINISH 는 열린 경로
sp.resolution_u = CURVE_RES_U

cu.use_path = True
cu.use_path_follow = True
cu.path_duration = TOTAL_FRAMES
cu.eval_time = 0.0

path = bpy.data.objects.new("PATH_Main", cu)
link_to(path, COL)
path.location = (0.0, 0.0, 0.0)
path.rotation_euler = (0.0, 0.0, 0.0)
path.scale = (1.0, 1.0, 1.0)
path.hide_render = True
path["length_m"] = PATH_LEN
path["min_radius_m"] = R_MIN_CURVE

# ---------------------------------------------------------------- 4. 차량 결선
root = bpy.data.objects.get("UGV_Root")
if root is None:
    raise RuntimeError(
        "UGV_Root 가 없다. 70_vehicle.py 를 먼저 실행해야 한다.\n"
        "실행 순서: 00 -> 10 -> 20 -> 30 -> 40 -> 50 -> 60 -> 55 -> 70 -> 80")

WHEEL_TAGS = ("FL", "FR", "RL", "RR")
WHEELS = [bpy.data.objects.get("UGV_Wheel_" + t) for t in WHEEL_TAGS]
missing = [t for t, w in zip(WHEEL_TAGS, WHEELS) if w is None]
if missing:
    raise RuntimeError("바퀴 오브젝트 누락: %s — 70_vehicle.py 를 다시 실행하라" % missing)
body = bpy.data.objects.get("UGV_Body")
sensor = bpy.data.objects.get("UGV_Sensor")

WHEEL_R = float(root.get("wheel_r", VS.get("wheel_r", 0.022)))
WHEELBASE = float(root.get("wheelbase", 0.124))
TRACK_W = float(root.get("track_width", 0.112))
FWD = str(root.get("forward_axis", "+X"))
FORWARD_AXIS = {"+X": 'FORWARD_X', "-X": 'TRACK_NEGATIVE_X',
                "+Y": 'FORWARD_Y', "-Y": 'TRACK_NEGATIVE_Y'}.get(FWD, 'FORWARD_X')
assert WHEEL_R > 1e-4, "wheel_r 이 비정상이다"

for ob in [root, body, sensor] + WHEELS:
    clear_anim(ob)
for c in list(root.constraints):
    root.constraints.remove(c)

# Follow Path 는 obmat = path_matrix @ object_matrix 로 합성된다.
# 루트의 로컬 변환이 경로 프레임에서 오프셋으로 먹으므로 반드시 항등으로 둔다.
root.location = (0.0, 0.0, 0.0)
root.rotation_euler = (0.0, 0.0, 0.0)
root.scale = (1.0, 1.0, 1.0)
root.delta_location = (0.0, 0.0, 0.0)
root.delta_rotation_euler = (0.0, 0.0, 0.0)

con = root.constraints.new('FOLLOW_PATH')
con.name = "UGV_FollowPath"
con.target = path
con.use_curve_follow = True        # 꺼져 있으면 차가 방향을 안 틀고 옆으로 간다
con.use_fixed_location = False     # eval_time 으로 구동
con.forward_axis = FORWARD_AXIS    # 이 차량은 전방이 +X 다
con.up_axis = 'UP_Z'
con.offset = 0.0
con.offset_factor = 0.0
con.influence = 1.0
con.mute = False

if body is not None:
    body.location = (0.0, 0.0, 0.0)
    body.rotation_euler = (0.0, 0.0, 0.0)
if sensor is not None:
    sensor.location = (0.0, 0.0, 0.0)
    sensor.rotation_euler = (0.0, 0.0, 0.0)
for w in WHEELS:
    w.rotation_euler = (0.0, 0.0, 0.0)

# ---------------------------------------------------------------- 5. 속도 곡선
DRIVE_SEC = (DRIVE_F1 - DRIVE_F0) / float(FPS)
FRAME_S, VGRID, DS, VSTAT = build_speed_profile(
    SAMP, ARC, PATH_LEN, CP_ARC, HAZ_ARC, DRIVE_SEC)

# eval_time 키: 정지 구간 2개 + 주행 구간 (12 프레임 간격 + 체크포인트 근방)
KEY_STRIDE = 12
key_frames = [1, DRIVE_F0]
k = DRIVE_F0 + KEY_STRIDE
while k < DRIVE_F1:
    key_frames.append(k)
    k += KEY_STRIDE
key_frames += [DRIVE_F1, TOTAL_FRAMES]
key_frames = sorted(set(key_frames))

KEYS = []
for f in key_frames:
    if f <= DRIVE_F0:
        s = 0.0
    elif f >= DRIVE_F1:
        s = PATH_LEN
    else:
        s = FRAME_S[f - DRIVE_F0]
    KEYS.append((f, s / PATH_LEN))

# --- 단조 검산 (역전되면 차가 후진한다) ---
assert all(KEYS[i][1] <= KEYS[i + 1][1] + 1e-12 for i in range(len(KEYS) - 1)), \
    "eval_time 역전"
moving = [(f, t) for f, t in KEYS if DRIVE_F0 <= f <= DRIVE_F1]
assert all(moving[i][1] < moving[i + 1][1] for i in range(len(moving) - 1)), \
    "주행 구간 eval_time 이 증가하지 않는다"
assert abs(KEYS[0][1]) < 1e-9 and abs(KEYS[-1][1] - 1.0) < 1e-9, \
    "eval_time 이 0..1 을 덮지 않는다"

fc_eval = bake_channel(cu, "eval_time", None,
                       [f for f, _ in KEYS],
                       [t * TOTAL_FRAMES for _, t in KEYS],
                       interp='BEZIER', handle='AUTO_CLAMPED')
# AUTO 핸들은 키 사이에서 오버슈트를 만들어 차가 잠깐 뒤로 갔다 온다.
if fc_eval is not None:
    for kp in fc_eval.keyframe_points:
        kp.interpolation = 'BEZIER'
        kp.handle_left_type = 'AUTO_CLAMPED'
        kp.handle_right_type = 'AUTO_CLAMPED'
    fc_eval.extrapolation = 'CONSTANT'
    fc_eval.update()

# ---------------------------------------------------------------- 6. 궤적 실측
# 컨스트레인트는 의존성 그래프가 평가되어야 위치에 반영된다.
# scene.frame_set() 없이 matrix_world 를 읽으면 전 프레임이 같은 값이 나와
# 바퀴 회전이 아예 생기지 않는다.
# 프레임 수만큼 의존성 그래프를 평가하므로 720 프레임에서 수십 초가 걸린다. 정상이다.
_t0 = time.time()
POS = [None] * (TOTAL_FRAMES + 1)
YAW = [0.0] * (TOTAL_FRAMES + 1)
FWDV = [(1.0, 0.0)] * (TOTAL_FRAMES + 1)
for f in range(1, TOTAL_FRAMES + 1):
    scene.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    try:
        mw = root.evaluated_get(dg).matrix_world
    except Exception:
        mw = root.matrix_world
    POS[f] = (mw.translation.x, mw.translation.y, mw.translation.z)
    fx, fy = mw[0][0], mw[1][0]          # 로컬 +X 의 월드 방향
    n = math.hypot(fx, fy)
    if n > 1e-9:
        FWDV[f] = (fx / n, fy / n)
    YAW[f] = math.atan2(fy, fx)
TRACE_SEC = time.time() - _t0

# yaw 언랩
for f in range(2, TOTAL_FRAMES + 1):
    d = YAW[f] - YAW[f - 1]
    while d > math.pi:
        YAW[f] -= 2.0 * math.pi
        d = YAW[f] - YAW[f - 1]
    while d < -math.pi:
        YAW[f] += 2.0 * math.pi
        d = YAW[f] - YAW[f - 1]

# 프레임별 이동/속도
STEP = [0.0] * (TOTAL_FRAMES + 1)
SPEED = [0.0] * (TOTAL_FRAMES + 1)
DIST = [0.0] * (TOTAL_FRAMES + 1)
DYAW = [0.0] * (TOTAL_FRAMES + 1)
reversals = 0
align_sum = 0.0
align_n = 0
for f in range(2, TOTAL_FRAMES + 1):
    dx = POS[f][0] - POS[f - 1][0]
    dy = POS[f][1] - POS[f - 1][1]
    d = math.hypot(dx, dy)
    STEP[f] = d
    SPEED[f] = d * FPS
    DIST[f] = DIST[f - 1] + d
    DYAW[f] = YAW[f] - YAW[f - 1]
    if d > 1e-5:
        ux, uy = dx / d, dy / d
        dot = ux * FWDV[f][0] + uy * FWDV[f][1]
        align_sum += dot
        align_n += 1
        if dot < 0.0:
            reversals += 1
SPEED[1] = SPEED[2]
ALIGN = align_sum / max(align_n, 1)

assert reversals == 0, "차량이 %d 프레임에서 후진한다 (eval_time 오버슈트 의심)" % reversals
assert ALIGN > 0.95, ("진행 방향과 차량 전방이 어긋난다 (평균 정렬 %.3f). "
                      "forward_axis 설정을 확인하라" % ALIGN)
zmax = max(abs(p[2]) for p in POS[1:])
assert zmax < 1e-4, "루트가 노면에서 %.4f m 떠 있다" % zmax

# ---------------------------------------------------------------- 7. 회피 창
# 하자드 최근접 호장(HAZ_INFO)을 실측 주행거리 DIST 로 프레임에 매핑한다.
AVOID_W = [0.0] * (TOTAL_FRAMES + 1)          # 프레임별 회피 창 세기 0..1
for nm, (s_h, dcen, hr) in HAZ_INFO.items():
    for f in range(1, TOTAL_FRAMES + 1):
        d = (DIST[f] - s_h) / AVOID_WINDOW
        AVOID_W[f] = max(AVOID_W[f], math.exp(-d * d))

# ---------------------------------------------------------------- 8. 조향각
# kappa = dyaw/ds. 정지 구간에서는 ds->0 이라 0 으로 둔다 (0/0 튐 방지).
KAPPA = [0.0] * (TOTAL_FRAMES + 1)
for f in range(2, TOTAL_FRAMES + 1):
    if STEP[f] > 2.0e-4:
        KAPPA[f] = DYAW[f] / STEP[f]
KAPPA[1] = KAPPA[2]
for _ in range(2):                                  # 곡률 잡음 제거
    KAPPA = [KAPPA[0]] + [(KAPPA[max(1, i - 1)] + 2.0 * KAPPA[i]
                           + KAPPA[min(TOTAL_FRAMES, i + 1)]) * 0.25
                          for i in range(1, TOTAL_FRAMES + 1)]

STEER = [0.0] * (TOTAL_FRAMES + 1)
tgt_prev = 0.0
for f in range(1, TOTAL_FRAMES + 1):
    tgt = steer_of(KAPPA[f], WHEELBASE, STEER_MAX)
    tgt_prev = tgt_prev + (tgt - tgt_prev) * STEER_ALPHA      # 조향기 1차 지연
    STEER[f] = tgt_prev
STEER_PEAK = max(abs(v) for v in STEER)

# ---------------------------------------------------------------- 9. 바퀴 회전
# 좌우 차동: v_wheel = v - yaw_rate * y_wheel  (좌측 y>0)
# 급코너에서 안쪽 바퀴가 눈에 띄게 느려진다 = "돌고 있다"가 읽힌다.
frames = list(range(1, TOTAL_FRAMES + 1))
WHEEL_Y = {"FL": +TRACK_W * 0.5, "RL": +TRACK_W * 0.5,
           "FR": -TRACK_W * 0.5, "RR": -TRACK_W * 0.5}
WHEEL_DIST = {}
for tag in WHEEL_TAGS:
    yw = WHEEL_Y[tag]
    acc = 0.0
    seq = [0.0]
    for f in range(2, TOTAL_FRAMES + 1):
        acc += STEP[f] - DYAW[f] * yw
        seq.append(acc)
    WHEEL_DIST[tag] = seq

WHEEL_RATIO = 1.0
for tag, w in zip(WHEEL_TAGS, WHEELS):
    wr = float(w.get("wheel_r", WHEEL_R))
    sign = float(w.get("roll_sign", 1.0))
    seq = WHEEL_DIST[tag]
    # rotation_euler 를 통째로 대입하지 않고 인덱스 0(로컬 X)만 다룬다.
    # 축을 월드 Y 로 세우는 90도는 delta_rotation_euler 에 들어 있다.
    bake_channel(w, "rotation_euler", 0, frames,
                 [sign * s / wr for s in seq], interp='LINEAR')
    if tag in ("FL", "FR"):
        # 로컬 Z = 조향축. 최종 회전이 R_delta @ R_local 이므로
        # R_delta(90° about Z) @ Rz(steer) @ Rx(spin) = Rz(90+steer) @ Rx(spin)
        # 즉 로컬 Z 값이 그대로 월드 조향각이 된다.
        bake_channel(w, "rotation_euler", 2, frames,
                     [STEER[f] for f in frames], interp='LINEAR')

WHEEL_REV = DIST[TOTAL_FRAMES] / (2.0 * math.pi * WHEEL_R)
# 헤어핀에서 좌우 바퀴가 얼마나 벌어지는가 (1.0 이면 차동 없음)
_k = max(range(2, TOTAL_FRAMES + 1),
         key=lambda f: abs(KAPPA[f]) if STEP[f] > 2.0e-4 else 0.0)
_vi = STEP[_k] - DYAW[_k] * (TRACK_W * 0.5)
_vo = STEP[_k] + DYAW[_k] * (TRACK_W * 0.5)
WHEEL_RATIO = min(99.0, max(abs(_vi), abs(_vo)) / max(min(abs(_vi), abs(_vo)), 1e-9))

# ---------------------------------------------------------------- 10. 차체 운동
# 롤: 좌회전(+yaw rate) 이면 원심력이 차체를 오른쪽으로 민다.
#     로컬 X 회전 +는 좌측(+Y)이 올라가는 방향 = 오른쪽으로 기움. 부호 +.
#     회피 창 안에서는 반응 문턱(A_LAT_REF)을 낮춰 같은 횡가속에도 더 기운다.
#     최대 진폭 ROLL_MAX 는 그대로다 — 과하면 장난감처럼 보인다.
# 피치: 감속(a<0) 이면 노즈 다이브. 로컬 Y 회전 +가 노즈 다운. 부호 -.
sp_s = [0.0] * (TOTAL_FRAMES + 1)
for f in range(1, TOTAL_FRAMES + 1):
    a = max(1, f - 1)
    b = min(TOTAL_FRAMES, f + 1)
    sp_s[f] = sum(SPEED[a:b + 1]) / float(b - a + 1)

roll_t = [0.0] * (TOTAL_FRAMES + 1)
pitch_t = [0.0] * (TOTAL_FRAMES + 1)
for f in range(2, TOTAL_FRAMES + 1):
    yaw_rate = DYAW[f] * FPS
    a_lat = sp_s[f] * yaw_rate
    a_lon = (sp_s[f] - sp_s[f - 1]) * FPS
    ref = A_LAT_REF / (1.0 + AVOID_ROLL_GAIN * AVOID_W[f])
    roll_t[f] = ROLL_MAX * math.tanh(a_lat / ref)
    pitch_t[f] = -PITCH_MAX * math.tanh(a_lon / A_LON_REF)
roll_t[1] = roll_t[2]
pitch_t[1] = pitch_t[2]

roll = [0.0] * (TOTAL_FRAMES + 1)
pitch = [0.0] * (TOTAL_FRAMES + 1)
for f in range(2, TOTAL_FRAMES + 1):        # 서스펜션 1차 지연 (즉답하면 기계처럼 보인다)
    roll[f] = roll[f - 1] + (roll_t[f] - roll[f - 1]) * SUSP_ALPHA
    pitch[f] = pitch[f - 1] + (pitch_t[f] - pitch[f - 1]) * SUSP_ALPHA


def smooth3(a):
    out = list(a)
    for i in range(2, len(a) - 1):
        out[i] = (a[i - 1] + 2.0 * a[i] + a[i + 1]) * 0.25
    return out


roll = smooth3(roll)
pitch = smooth3(pitch)
ROLL_PEAK = max(abs(v) for v in roll)
PITCH_PEAK = max(abs(v) for v in pitch)

# ---------------------------------------------------------------- 11. 하자드 이벤트
def nearest_frame(qx, qy, f0=1, f1=None):
    f1 = TOTAL_FRAMES if f1 is None else f1
    bf, bd = f0, 1e9
    for f in range(f0, f1 + 1):
        d = math.hypot(POS[f][0] - qx, POS[f][1] - qy)
        if d < bd:
            bd, bf = d, f
    return bf, bd


def corridor_offset(x, y):
    """(회랑 이름, 중앙선 부호 있는 이탈). 어느 회랑에도 안 들면 (None, None)."""
    best = None
    for nm, ax, c, rng, half in CORRIDORS:
        u = y if ax == 'x' else x
        if not (rng[0] - 0.05 <= u <= rng[1] + 0.05):
            continue
        off = (x if ax == 'x' else y) - c
        if abs(off) > half:
            continue
        if best is None or abs(off) < abs(best[1]):
            best = (nm, off)
    return best if best else (None, None)


def avoid_event(name, kind, q, hr, swept_key):
    """회피 이벤트 하나. 진입/정점/이탈 프레임과 '얼마나 비켰는가'를 실측한다."""
    bf, bd = nearest_frame(q[0], q[1])
    s_h = DIST[bf]
    f0 = f1 = bf
    while f0 > 1 and abs(DIST[f0] - s_h) < AVOID_WINDOW:
        f0 -= 1
    while f1 < TOTAL_FRAMES and abs(DIST[f1] - s_h) < AVOID_WINDOW:
        f1 += 1
    # 진입점-이탈점 직선에서 얼마나 벗어났는가 = 눈에 보이는 '회피 폭'
    ax, ay = POS[f0][0], POS[f0][1]
    bx, by = POS[f1][0], POS[f1][1]
    L = math.hypot(bx - ax, by - ay)
    swing = 0.0
    if L > 1e-6:
        ux, uy = (bx - ax) / L, (by - ay) / L
        for f in range(f0, f1 + 1):
            px, py = POS[f][0] - ax, POS[f][1] - ay
            swing = max(swing, abs(-uy * px + ux * py))
    # 속도는 '진입 전 최고'가 아니라 '창 주변 최고' 와 비교한다. 코너 직후에
    # 하자드가 오면 진입 전 속도가 이미 낮아서 감속이 없는 것처럼 보이기 때문.
    w0 = max(1, f0 - 25)
    w1 = min(TOTAL_FRAMES, f1 + 25)
    v_apex = SPEED[bf]
    v_win = max(SPEED[w0:w1 + 1] or [0.0])
    v_before = max(SPEED[w0:f0 + 1] or [0.0])
    v_after = max(SPEED[f1:w1 + 1] or [0.0])
    cname, coff = corridor_offset(POS[bf][0], POS[bf][1])
    return {
        "name": name, "kind": kind,
        "pos": [round(q[0], 4), round(q[1], 4)], "r": round(hr, 4),
        "frame_enter": int(f0), "frame_apex": int(bf), "frame_exit": int(f1),
        "time_enter_s": round((f0 - 1) / float(FPS), 3),
        "time_apex_s": round((bf - 1) / float(FPS), 3),
        "time_exit_s": round((f1 - 1) / float(FPS), 3),
        "center_distance_m": round(bd, 4),
        "swept_clearance_m": round(SWEPT[swept_key][0], 4) if swept_key in SWEPT else None,
        "lateral_swing_m": round(swing, 4),
        "corridor": cname,
        "corridor_offset_at_apex_m": (round(coff, 4) if coff is not None else None),
        "speed_before_mps": round(v_before, 3),
        "speed_apex_mps": round(v_apex, 3),
        "speed_after_mps": round(v_after, 3),
        "speed_window_max_mps": round(v_win, 3),
        "speed_dip_pct": round(max(0.0, 100.0 * (1.0 - v_apex / max(v_win, 1e-6))), 1),
        "roll_peak_deg": round(math.degrees(max(abs(r) for r in roll[f0:f1 + 1])), 2),
        "steer_peak_deg": round(math.degrees(max(abs(s) for s in STEER[f0:f1 + 1])), 2),
    }


AVOID_EVENTS = []
POTHOLE_EVENTS = []
for ph in SPEC["potholes"]:
    key = "pothole_%d" % ph["id"]
    ev = avoid_event(key, "pothole", tuple(ph["pos"]), float(ph["r"]), key)
    ev["required_m"] = round(ph["r"] + HALF_W + POTHOLE_MARGIN, 4)
    ev["near_pass"] = bool(ev["center_distance_m"] < POTHOLE_NEAR)
    AVOID_EVENTS.append(ev)
    POTHOLE_EVENTS.append({"id": ph["id"], "pos": ev["pos"], "r": ph["r"],
                           "frame": ev["frame_apex"], "time_s": ev["time_apex_s"],
                           "min_distance_m": ev["center_distance_m"],
                           "required_m": ev["required_m"],
                           "near_pass": ev["near_pass"]})
for br in SPEC["barriers"]:
    key = "barrier_%d" % br["id"]
    AVOID_EVENTS.append(avoid_event(
        key, "barrier", tuple(br["pos"]),
        max(br["size"][0], br["size"][1]) * 0.5, key))
AVOID_EVENTS.sort(key=lambda e: e["frame_apex"])

# ---------------------------------------------------------------- 12. 차체 키
SHAKE_TARGETS = [ob for ob in (body, sensor) if ob is not None]
for ob in SHAKE_TARGETS:
    bake_channel(ob, "rotation_euler", 0, frames, roll[1:], interp='LINEAR')
    bake_channel(ob, "rotation_euler", 1, frames, pitch[1:], interp='LINEAR')
    # Z 는 키 2개만 두고 노면 진동은 F커브 노이즈 모디파이어로 준다.
    fz = bake_channel(ob, "location", 2, [1, TOTAL_FRAMES], [0.0, 0.0], interp='LINEAR')
    add_noise_modifier(fz, ROAD_NOISE_Z, 2.5, phase=3.0)
    fr = _find_fcurve(ob, "rotation_euler", 0)
    add_noise_modifier(fr, ROAD_NOISE_ROLL, 3.0, phase=11.0)
    for ev in POTHOLE_EVENTS:
        if not ev["near_pass"]:
            continue
        f0 = max(1, ev["frame"] - 26)
        f1 = min(TOTAL_FRAMES, ev["frame"] + 26)
        add_noise_modifier(fz, POTHOLE_NOISE_Z, 1.1, phase=7.0 * ev["id"],
                           frame_range=(f0, f1), blend=(10.0, 12.0))
        add_noise_modifier(fr, POTHOLE_NOISE_ROLL, 1.3, phase=5.0 * ev["id"],
                           frame_range=(f0, f1), blend=(10.0, 12.0))

# ---------------------------------------------------------------- 13. 통과 실측
EVENTS = []
ORDER = ["START", "ALPHA", "BRAVO", "CHARLIE", "FINISH"]
CP_SRC = dict(TAG_SRC)

search_lo = 1
for nm in ORDER:
    qx, qy = CP_SRC[nm]
    if nm == "START":
        f, d = 1, math.hypot(POS[1][0] - qx, POS[1][1] - qy)
    else:
        # search_lo 이후만 본다 — 경로가 두 번 스치는 지점에서 순서가 뒤집히지 않게.
        f, d = nearest_frame(qx, qy, search_lo, TOTAL_FRAMES)
    search_lo = max(search_lo, f)
    EVENTS.append({"name": nm, "frame": int(f),
                   "time_s": round((f - 1) / float(FPS), 3),
                   "spec_pos": [round(qx, 4), round(qy, 4)],
                   "measured_pos": [round(POS[f][0], 4), round(POS[f][1], 4)],
                   "distance_m": round(d, 4),
                   "speed_mps": round(SPEED[f], 4),
                   "heading_rad": round(YAW[f], 4),
                   "progress": round(DIST[f] / max(DIST[TOTAL_FRAMES], 1e-9), 4)})

for ev in EVENTS:
    if ev["name"] in ("ALPHA", "BRAVO", "CHARLIE"):
        assert ev["distance_m"] <= CP_TOL, \
            "%s 통과 실측 거리 %.4f m > 허용 %.2f m" % (ev["name"], ev["distance_m"], CP_TOL)
assert EVENTS[0]["frame"] < EVENTS[1]["frame"] < EVENTS[2]["frame"] \
    < EVENTS[3]["frame"] <= EVENTS[4]["frame"], "체크포인트 통과 순서가 어긋났다"

# 제어점별 통과 프레임 -> 카메라 컷 구간
CTRL_FRAMES = []
lo = 1
for i in range(len(PTS)):
    f, d = nearest_frame(PTS[i][0], PTS[i][1], lo, TOTAL_FRAMES)
    lo = max(lo, f)
    CTRL_FRAMES.append({"index": i, "tag": TAGS[i], "frame": int(f),
                        "pos": [round(PTS[i][0], 4), round(PTS[i][1], 4)],
                        "note": NOTES[i], "distance_m": round(d, 4)})

# 제어점 인덱스는 PATH_PTS 를 고치면 함께 움직인다. 구간 정의도 같이 갱신할 것.
SEG_DEF = [("GRID_HOLD", 0, 0, "출발 대기 — 정지 상태, 조감/설정 샷"),
           ("LAUNCH", 0, 2, "발진 가속, START 라인 통과 + ALPHA"),
           ("NORTH_RUN", 2, 4, "상단 회랑 최고속 구간"),
           ("EAST_SWEEP", 4, 7, "우측 코너 연속 감속"),
           ("CENTER_CORRIDOR", 7, 10, "중앙 십자 회랑 통과"),
           ("BRAVO_HAIRPIN", 10, 12, "BRAVO 급코너 — 최저속, 슬로모 후보"),
           ("HAZARD_GATE", 12, 15, "포트홀1 북측 / 배리어1 남측 게이트 — 회피 하이라이트"),
           ("WEST_TRAVERSE", 15, 18, "좌측 회랑 하강"),
           ("CHARLIE_TURN", 18, 19, "좌하단 코너 + CHARLIE 통과"),
           ("POTHOLE_DODGE", 19, 22, "포트홀2 남측 회피 — 감속·비킴·복귀"),
           ("SOUTH_RUN", 22, 25, "하단 회랑 중앙 재가속"),
           ("FINISH_BRAKE", 25, 27, "FINISH 활강 감속 정지")]
SEGMENTS = []
for name, i0, i1, note in SEG_DEF:
    if name == "GRID_HOLD":
        f0, f1 = 1, DRIVE_F0
    else:
        f0 = DRIVE_F0 if name == "LAUNCH" else CTRL_FRAMES[i0]["frame"]
        f1 = CTRL_FRAMES[i1]["frame"] if i1 < len(CTRL_FRAMES) else TOTAL_FRAMES
        if name == "FINISH_BRAKE":
            f1 = TOTAL_FRAMES
    SEGMENTS.append({"name": name, "frame_start": int(f0), "frame_end": int(f1),
                     "duration_s": round((f1 - f0) / float(FPS), 3), "note": note})

STRIDE = 6
SAMPLES_OUT = []
for f in range(1, TOTAL_FRAMES + 1, STRIDE):
    SAMPLES_OUT.append({"f": f,
                        "x": round(POS[f][0], 4), "y": round(POS[f][1], 4),
                        "yaw": round(YAW[f], 4), "v": round(SPEED[f], 3)})
if SAMPLES_OUT[-1]["f"] != TOTAL_FRAMES:
    f = TOTAL_FRAMES
    SAMPLES_OUT.append({"f": f, "x": round(POS[f][0], 4), "y": round(POS[f][1], 4),
                        "yaw": round(YAW[f], 4), "v": round(SPEED[f], 3)})

MOVE_SPEEDS = [SPEED[f] for f in range(DRIVE_F0 + 4, DRIVE_F1 - 4)]

# ---------------------------------------------------------------- 14. timeline
TIMELINE = {
    "_meta": {
        "name": "MAICON UGV 주행 타임라인",
        "author": "motion-director",
        "source": "80_motion.py 가 실행 시점에 궤적을 실측해 생성한다. 손으로 고치지 말 것",
        "generated_from": {"script": "80_motion.py", "spec_version": SPEC["_meta"]["version"]},
        "note": "frame 은 1-based. 카메라 컷은 events/avoidance_events/segments 를 기준으로 잡는다",
    },
    "fps": FPS,
    "total_frames": TOTAL_FRAMES,
    "frame_start": 1,
    "frame_end": TOTAL_FRAMES,
    "duration_s": round(TOTAL_FRAMES / float(FPS), 3),
    "hold": {"start": [1, DRIVE_F0], "end": [DRIVE_F1, TOTAL_FRAMES],
             "note": "정지 구간. 조감 설정 샷과 종료 타이틀에 쓸 수 있다"},
    "path": {
        "object": "PATH_Main",
        "length_m": round(PATH_LEN, 4),
        "control_points": len(PTS),
        "closed": False,
        "source": ("80_motion.py PATH_PTS. 스펙 path 22점 -> 28점. 태그 5점(START/ALPHA/"
                   "BRAVO/CHARLIE/FINISH)은 스펙 좌표 그대로이고 assert 로 검산한다. "
                   "태그 없는 점만 회랑 중앙 정렬과 하자드 회피를 위해 재배치했다."),
        "min_radius_m": round(R_MIN_CURVE, 4),
        "min_radius_target_m": R_MIN_TARGET,
        "min_radius_note": R_MIN_NOTE,
        "wall_note": WALL_NOTE,
        "control_point_moves": {str(i): [round(d[0], 4), round(d[1], 4)]
                                for i, d in sorted(MOVED.items())},
    },
    "vehicle": {
        "root": "UGV_Root", "body": "UGV_Body", "sensor": "UGV_Sensor",
        "cam_anchor": "UGV_Cam",
        "wheels": ["UGV_Wheel_FL", "UGV_Wheel_FR", "UGV_Wheel_RL", "UGV_Wheel_RR"],
        "forward_axis": FWD, "wheel_r_m": WHEEL_R,
        "wheelbase_m": WHEELBASE, "track_width_m": TRACK_W,
        "steer_max_deg": round(math.degrees(STEER_MAX), 1),
        "steer_channel": "UGV_Wheel_FL/FR rotation_euler[2] (앞바퀴만)",
        "wheel_drive": "좌우 차동 (v_wheel = v - yaw_rate * y_wheel)",
        "cam_anchor_parent": "UGV_Root",
        "cam_anchor_note": ("UGV_Cam 은 루트에 붙어 있어 차체 롤/피치/진동을 받지 않는다 "
                            "(짐벌 고정 FPV). 흔들리는 1인칭을 원하면 UGV_Body 로 부모를 바꿔라"),
    },
    "speed": {
        "unit": "m/s",
        "mean_mps": round(PATH_LEN / DRIVE_SEC, 4),
        "max_mps": round(max(MOVE_SPEEDS), 4),
        "min_moving_mps": round(min(MOVE_SPEEDS), 4),
        "profile": ("v = min(V_MAX*cap, sqrt(A_LAT/kappa)) + 종방향 가감속 한계. "
                    "cap = min(체크포인트 딥, 하자드 딥). 하자드 딥은 비대칭 "
                    "(진입 sigma %.2f / 이탈 sigma %.2f) 이라 미리 감속하고 곧바로 재가속한다."
                    % (HAZ_SIG_B, HAZ_SIG_A)),
        "v_max_param": V_MAX, "a_lat": A_LAT, "a_acc": A_ACC, "a_dec": A_DEC,
        "cp_dip": CP_DIP, "hazard_dip": HAZ_DIP,
    },
    "events": EVENTS,
    "avoidance_events": AVOID_EVENTS,
    "pothole_events": POTHOLE_EVENTS,
    "segments": SEGMENTS,
    "control_point_frames": CTRL_FRAMES,
    "samples": {"stride": STRIDE,
                "fields": ["f", "x", "y", "yaw", "v"],
                "data": SAMPLES_OUT},
    "qa": {
        "measured": True,
        "checkpoint_tolerance_m": CP_TOL,
        "checkpoint_max_distance_m": round(
            max(e["distance_m"] for e in EVENTS if e["name"] in ("ALPHA", "BRAVO", "CHARLIE")), 4),
        "backward_frames": reversals,
        "heading_alignment": round(ALIGN, 4),
        "root_z_max_abs_m": round(zmax, 6),
        "eval_time_keys": len(KEYS),
        "eval_time_monotonic": True,
        "wheel_revolutions": round(WHEEL_REV, 2),
        "wheel_speed_ratio_at_tightest": round(WHEEL_RATIO, 2),
        "roll_peak_deg": round(math.degrees(ROLL_PEAK), 3),
        "pitch_peak_deg": round(math.degrees(PITCH_PEAK), 3),
        "steer_peak_deg": round(math.degrees(STEER_PEAK), 3),
        "road_noise_z_m": ROAD_NOISE_Z,
        "clearance_centerline": {n: {"distance_m": round(v[0], 4),
                                     "required_m": round(v[1], 4),
                                     "margin_m": round(v[0] - v[1], 4)}
                                 for n, v in sorted(CLEAR.items(),
                                                    key=lambda kv: kv[1][0] - kv[1][1])[:6]},
        "clearance_swept_body": {n: round(v[0], 4)
                                 for n, v in sorted(SWEPT.items(),
                                                    key=lambda kv: kv[1][0])[:8]},
        "clearance_swept_note": ("앞바퀴 조향 %.0f° 를 실루엣에 반영한 값이다."
                                 % math.degrees(STEER_MAX)),
        "arena_wall_min_m": round(WALL_MIN, 4),
        "arena_wall_exposure_below_0p03_m": round(WALL_EXPOSURE, 3),
        "corridor_offsets": CORRIDOR_QA,
        "checkpoint_curve_distance_m": {k: round(v, 5) for k, v in CP_ON_PATH.items()},
    },
    "render_hint": {
        "motion_blur": True,
        "shutter": 0.5,
        "why": ("최고속 %.2f m/s 에서 바퀴가 프레임당 %.2f 회전한다. 트레드 러그가 14개라 "
                "모션 블러 없이는 바퀴가 거꾸로 도는 스트로브가 보인다."
                % (max(MOVE_SPEEDS), max(MOVE_SPEEDS) / (2.0 * math.pi * WHEEL_R) / FPS)),
    },
}

TIMELINE_PATH = os.path.join(WORKSPACE, "spec", "timeline.json")
with open(TIMELINE_PATH, "w", encoding="utf-8") as fp:
    json.dump(TIMELINE, fp, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------- 15. 마무리
scene.frame_set(1)

print("[80_motion] --- 속도 ---")
print("  주행 %d~%d 프레임 (%.2f s) / 평균 %.3f m/s / 최고 %.3f m/s / 최저(주행중) %.3f m/s"
      % (DRIVE_F0, DRIVE_F1, DRIVE_SEC, PATH_LEN / DRIVE_SEC,
         max(MOVE_SPEEDS), min(MOVE_SPEEDS)))
print("  eval_time 키 %d개 (AUTO_CLAMPED) / 단조 검산 통과 / 후진 프레임 %d"
      % (len(KEYS), reversals))
print("[80_motion] --- 부수 운동 ---")
print("  바퀴 총 회전 %.2f rev (r=%.3f m) / 최급코너 좌우 굴림비 %.2f : 1"
      % (WHEEL_REV, WHEEL_R, WHEEL_RATIO))
print("  롤 최대 %.2f° / 피치 최대 %.2f° / 조향 최대 %.2f° / 노면 진동 %.1f mm"
      % (math.degrees(ROLL_PEAK), math.degrees(PITCH_PEAK),
         math.degrees(STEER_PEAK), ROAD_NOISE_Z * 1000.0))
print("  전방 정렬 %.4f (1.0 = 완전 일치) / 루트 Z 최대 %.6f m / 궤적 실측 %.1f s"
      % (ALIGN, zmax, TRACE_SEC))
print("[80_motion] --- 통과 실측 ---")
for ev in EVENTS:
    print("  %-8s frame %4d (%6.2f s)  오차 %.4f m  속도 %.3f m/s"
          % (ev["name"], ev["frame"], ev["time_s"], ev["distance_m"], ev["speed_mps"]))
print("[80_motion] --- 회피 실측 (감속 -> 비킴 -> 재가속) ---")
for ev in AVOID_EVENTS:
    _c = ev["corridor_offset_at_apex_m"]
    print("  %-10s f%4d~%4d (정점 %4d) | 중심거리 %.3f 실루엣 %.4f | 비킴 %.3f m"
          "%s | v %.2f -> %.2f -> %.2f (창 최고 %.2f, 딥 %.0f%%) | 롤 %.1f° 조향 %.1f°"
          % (ev["name"], ev["frame_enter"], ev["frame_exit"], ev["frame_apex"],
             ev["center_distance_m"],
             ev["swept_clearance_m"] if ev["swept_clearance_m"] is not None else -1.0,
             ev["lateral_swing_m"],
             (" / 회랑중앙 %+.3f" % _c) if _c is not None else "",
             ev["speed_before_mps"], ev["speed_apex_mps"], ev["speed_after_mps"],
             ev["speed_window_max_mps"], ev["speed_dip_pct"],
             ev["roll_peak_deg"], ev["steer_peak_deg"]))

print("[80_motion] PATH_Main(%d pts, %.3f m) + FollowPath(%s) | %d frames @%dfps "
      "| wheels=4(차동+조향) | timeline.json 갱신 -> %s"
      % (len(PTS), PATH_LEN, FORWARD_AXIS, TOTAL_FRAMES, FPS,
         os.path.relpath(TIMELINE_PATH, os.path.dirname(WORKSPACE))))
