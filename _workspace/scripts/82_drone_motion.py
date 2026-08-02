# -*- coding: utf-8 -*-
"""
82_drone_motion.py — 정찰 드론 비행 애니메이션 (motion-director 산출)

산출물
    DRN_Root                  위치 3축 + 자세 3축 키프레임 (720 프레임)
    DRN_Rotor_{FL,FR,RL,RR}   rotation_euler[2] 회전 (spin_dir 반영, 전 구간)
    DPATH_Main                비행 경로 시각화 커브 (렌더 제외, QA 용)
    spec/drone_timeline.json  드론 이벤트 프레임 (실측값)

선행: 75_drone.py (DRN_* 부품), 40_sectors.py (화재 SEC_02 / SEC_09)
      80_motion.py 는 필수가 아니지만 있으면 timeline.json 을 읽어 UGV 이벤트와
      겹치는지 교차 점검한다.

--------------------------------------------------------------------------
설계 메모
--------------------------------------------------------------------------
1) 시간 배분은 UGV(720 프레임)와 병행하도록 고정되어 있다. 영상 길이를 늘리지 않는다.
       1~ 110  헬리패드 대기 -> 수직 이륙
     110~ 300  Sector 2 화재로 이동 + 접근
     300~ 360  FIRE_2 호버 (촬영)
     360~ 500  Sector 9 화재로 이동
     500~ 560  FIRE_9 호버 (촬영)
     560~ 680  복귀
     680~ 720  수직 하강 · 착륙

2) **고도를 올린 근거 (스펙 웨이포인트 z=0.62 를 그대로 쓰면 충돌한다).**
   같은 검산기(이 파일 하단 clearance())로 스펙 웨이포인트를 재면:
       FIRE_2_APPROACH  0.138 m   (SEC_02 동체)
       FIRE_2_SHOOT     0.031 m   (SEC_02 연기 기둥)
       FIRE_9_SHOOT     0.079 m   (SEC_09 연기 기둥)
   세 곳 모두 요구치 0.15 m 미달이다. 원인은 두 가지다.
     - 연기 기둥이 z 0.579~0.977 (SEC_02) / 0.456~0.757 (SEC_09) 를 채운다.
       순항고도 0.62 는 두 기둥의 **한가운데**다.
     - 건물 최고점이 0.643 m 라 순항고도 0.62 는 가장 높은 동(SEC_05)보다 낮다.
   해법으로 **수평 우회 대신 상승**을 택했다. 이유:
     - 하방 짐벌(DRN_Cam, -Z 나디르)로 화재를 촬영하는 임무다. 옆으로 비키면
       0.33 m 이상 떨어져야 안전한데, 그 거리에서 나디르 카메라는 화재를
       프레임에 담지 못한다 (광축에서 60° 밖).
     - z=1.20 에서 화재동 옥상(0.61)까지 0.59 아래, 수평 0.22 → 광축에서 20°.
       표준 화각에 화재동과 연기 기둥 상단이 함께 들어온다.
   연기 정점 위로 넘어가려면 1.28 m 이상이 필요한데(정점 0.977 + 상단 반경
   0.151 + 여유 0.15), 그러면 기둥 바로 위 상승기류에 들어간다. 그래서
   "정점보다 살짝 높고 축에서 0.22 m 비낀" 위치를 골랐다.

3) 스펙 대비 웨이포인트 변경 (XY 는 최소로, Z 위주로 조정)
       FIRE_2_APPROACH  (-0.22, 0.79, 0.62) -> (-0.22, 0.79, 1.15)   z +0.53
       FIRE_2_SHOOT     ( 0.03, 0.87, 0.62) -> ( 0.03, 0.88, 1.20)   z +0.58, y +0.01
       TRANSIT          ( 0.60,-0.40, 0.62) -> ( 0.60,-0.40, 0.75)   z +0.13
       FIRE_9_SHOOT     ( 1.30,-0.89, 0.62) -> ( 1.30,-0.95, 1.05)   z +0.43, y -0.06
       RETURN           (-1.55, 0.60, 0.62) -> (-1.55, 0.60, 0.56)   z -0.06 (착륙 준비)
       OVER_HOME        (-1.95, 0.80, 0.62) -> (-1.95, 0.80, 0.40)   z -0.22 (하강 준비)
   HOME / TAKEOFF / LANDED 는 스펙 그대로다. 이륙과 착륙은 XY 고정 = 완전 수직.
   TRANSIT z 를 0.75 로 올린 것은 SEC_05 옥상(0.643)을 넘기 위해서다.
   OVER_HOME 을 0.40 으로 낮춘 것은 착륙 속도 때문이다 — 0.62 에서 40 프레임
   만에 내려오면 접지 직전 0.70 m/s 로 떨어져 '추락'처럼 보인다. 0.40 이면 0.45 m/s.

4) 이동 프로파일은 사다리꼴(가속 -> 등속 -> 감속)이다. smoothstep 한 방으로
   전 구간을 덮으면 속도가 계속 변해 기체 기울기가 쉬지 않고 흔들린다.
   사다리꼴이면 "기울여 출발 -> 수평 순항 -> 반대로 기울여 정지" 가 또렷하다.
   쿼드콥터가 기울여서 이동한다는 사실이 그림으로 읽히는 지점이다.

5) 자세
     - 기수(yaw)  수평 속도가 있으면 진행 방향. 호버/수직 구간은 직전 값 유지.
                  착륙 직전에는 헬리패드 기준 자세(초기 yaw)로 되돌린다.
     - 피치       가속하면 기수를 숙인다(로컬 Y 회전 +가 노즈 다운).
                  등속에서도 항력분만큼 약간 숙인 채로 간다 (약 4°).
     - 롤         횡가속 방향으로 뱅크. 선회할 때만 나온다.
     - 호버       가속·속도 0 이므로 자동으로 기울기 0 이 된다 (강제하지 않는다).

6) 로터는 전 구간 돈다. spin_dir(FL=+1 FR=-1 RL=-1 RR=+1, 대각 동일)을 곱해
   반토크 배치를 지킨다. 프레임당 회전각을 149°(비행) / 20°(아이들)로 잡았다.
   블레이드가 2장(180° 대칭)이라 프레임당 180° 근처면 프롭이 멈춰 보인다.
   149° 는 그 함정에서 충분히 떨어져 있고 정방향으로 읽힌다.
"""

import bpy
import json
import math
import os

WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
exec(open(os.path.join(WORKSPACE, "scripts", "00_common.py")).read())

# ---------------------------------------------------------------- 타이밍
FPS = 30
TOTAL_FRAMES = 720

F_IDLE_END = 48          # 이 프레임까지 패드 위 정지
F_SPOOL0, F_SPOOL1 = 22, 46      # 로터 스풀업
F_TAKEOFF_END = 110
F_SHOOT2 = (300, 360)
F_SHOOT9 = (500, 560)
F_TRANSIT_END = 500
F_RETURN_END = 680
F_YAW_HOME0, F_YAW_HOME1 = 655, 715   # 착륙 자세로 기수 정렬

# ---------------------------------------------------------------- 비행 상수
TILT_MAX = math.radians(10.0)    # 기체 최대 기울기 (요구 5~10°)
TILT_A_REF = 0.60                # 이 종가속에서 tanh 인자가 1
TILT_V_REF = 2.20                # 항력분 — 순항 0.9 m/s 에서 약 4°
TILT_ALPHA = 0.30                # 자세 1차 지연 (즉답하면 로봇처럼 보인다)
YAW_ALPHA = 0.22                 # 기수 1차 지연
YAW_V_MIN = 0.030                # 이 수평속도 미만이면 기수를 유지한다

RAMP_IN, RAMP_OUT = 0.25, 0.25   # 사다리꼴 가속/감속 구간 비율

OMEGA_IDLE = 10.5                # rad/s — 프레임당 20°
OMEGA_FLIGHT = 72.0              # rad/s — 프레임당 137° (180° 스트로브 회피)
OMEGA_CLIMB = 12.0               # 상승률 1 m/s 당 추가 rad/s (최대 147°/frame)
OMEGA_DEG_LIMIT = 165.0          # 프레임당 회전각 상한 — 180° 에 붙으면 프롭이 멈춰 보인다

HOVER_DRIFT = 0.003              # 호버 표류 ±3 mm
HOVER_DRIFT_SCALE = 5.0
AIR_JITTER_ROT = math.radians(0.35)   # 비행 중 미세 자세 흔들림
AIR_JITTER_LOC = 0.0012

# ---------------------------------------------------------------- 검산 상수
CLEAR_REQ = 0.150        # 화재 건물/연기와 최소 이격
MAST = 0.100             # 옥상 구조물 여유 (최고 건물 0.55 + 0.093 = 0.643)
# 40_sectors.py 화재 상수 — 연기 정점은 40_sectors 실행 로그의 실측값이다.
SMOKE_H = (0.60, 0.18)
SMOKE_R0 = 0.014
SMOKE_R1 = (0.052, 0.045)
SMOKE_LEAN = 0.10
SMOKE_SWAY = 0.018
APEX_MEASURED = {2: 0.977, 9: 0.757}

DR = SPEC.get("drone", {})
HOME = tuple(float(v) for v in DR.get("home", [-1.95, 0.80, 0.0]))
CRUISE_Z = float(DR.get("cruise_z", 0.62))

# (이름, f0, f1, 모드, [경유점...])  모드: hold/vert/fly/hover
PHASES = [
    ("IDLE",     1,   F_IDLE_END,    'hold',  [HOME]),
    ("TAKEOFF",  F_IDLE_END, F_TAKEOFF_END, 'vert',
     [HOME, (HOME[0], HOME[1], CRUISE_Z)]),
    ("OUTBOUND", F_TAKEOFF_END, F_SHOOT2[0], 'fly',
     [(HOME[0], HOME[1], CRUISE_Z),
      (-1.180, 0.800, 0.900),          # 블록 A 상공 — SEC_01 옥상 위로 넘는다
      (-0.220, 0.790, 1.150),          # FIRE_2_APPROACH (스펙 XY, z 상향)
      (0.030, 0.880, 1.200)]),         # FIRE_2_SHOOT
    ("SHOOT_2",  F_SHOOT2[0], F_SHOOT2[1], 'hover', [(0.030, 0.880, 1.200)]),
    ("TRANSIT",  F_SHOOT2[1], F_TRANSIT_END, 'fly',
     [(0.030, 0.880, 1.200),
      (0.600, -0.400, 0.750),          # TRANSIT (스펙 XY, SEC_05 옥상 위)
      (1.300, -0.950, 1.050)]),        # FIRE_9_SHOOT
    ("SHOOT_9",  F_SHOOT9[0], F_SHOOT9[1], 'hover', [(1.300, -0.950, 1.050)]),
    ("RETURN",   F_SHOOT9[1], F_RETURN_END, 'fly',
     [(1.300, -0.950, 1.050),
      (0.300, -0.300, 0.820),          # 중앙 상공 — SEC_06 옥상 위로 넘는다
      (-1.550, 0.600, 0.560),          # RETURN
      (HOME[0], HOME[1], 0.400)]),     # OVER_HOME (하강 준비 고도)
    ("LAND",     F_RETURN_END, TOTAL_FRAMES, 'vert',
     [(HOME[0], HOME[1], 0.400), HOME]),
]

WP_TAGS = {   # 스펙 웨이포인트가 실제로 어느 프레임에 대응하는지 (실측으로 갱신됨)
    "HOME": (HOME[0], HOME[1], HOME[2]),
    "TAKEOFF": (HOME[0], HOME[1], CRUISE_Z),
    "FIRE_2_APPROACH": (-0.220, 0.790, 1.150),
    "FIRE_2_SHOOT": (0.030, 0.880, 1.200),
    "TRANSIT": (0.600, -0.400, 0.750),
    "FIRE_9_SHOOT": (1.300, -0.950, 1.050),
    "RETURN": (-1.550, 0.600, 0.560),
    "OVER_HOME": (HOME[0], HOME[1], 0.400),
    "LANDED": (HOME[0], HOME[1], HOME[2]),
}


# ==================================================================
# TRAJECTORY CORE BEGIN — bpy 비의존
# ==================================================================
def smoothstep(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3.0 - 2.0 * u)


def trapezoid(u, ra=RAMP_IN, rd=RAMP_OUT):
    """사다리꼴 속도 프로파일의 이동률 s(u). v(0)=v(1)=0, 중간은 등속.

    v(u) = smoothstep(u/ra) / 1 / smoothstep((1-u)/rd) 를 적분해 정규화한 값.
    smoothstep 하나로 전 구간을 덮는 것보다 최고속이 낮고(1.33/T vs 1.5/T)
    등속 구간이 생겨 기체 기울기가 "가속 -> 수평 -> 감속"으로 또렷해진다.
    """
    u = max(0.0, min(1.0, u))
    k = 1.0 - 0.5 * ra - 0.5 * rd            # ∫v du (정규화 계수)

    def area(x):
        if x <= 0.0:
            return 0.0
        if x < ra:
            t = x / ra
            return ra * (t ** 3 - 0.5 * t ** 4)          # ∫smoothstep
        a = ra * 0.5
        if x <= 1.0 - rd:
            return a + (x - ra)
        a += (1.0 - rd - ra)
        t = (1.0 - x) / rd
        return a + rd * 0.5 - rd * (t ** 3 - 0.5 * t ** 4)

    return min(1.0, max(0.0, area(u) / k))


def catmull(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    return tuple(0.5 * ((2.0 * p1[i]) + (-p0[i] + p2[i]) * t
                        + (2.0 * p0[i] - 5.0 * p1[i] + 4.0 * p2[i] - p3[i]) * t2
                        + (-p0[i] + 3.0 * p1[i] - 3.0 * p2[i] + p3[i]) * t3)
                 for i in range(3))


def poly_eval(pts, u):
    """경유점을 정확히 통과하는 Catmull-Rom (양 끝은 복제로 클램프)."""
    n = len(pts)
    if n == 1:
        return tuple(pts[0])
    if n == 2:
        return tuple(pts[0][i] + (pts[1][i] - pts[0][i]) * u for i in range(3))
    x = max(0.0, min(1.0 - 1e-9, u)) * (n - 1)
    i = int(x)
    t = x - i
    return catmull(pts[max(0, i - 1)], pts[i],
                   pts[min(n - 1, i + 1)], pts[min(n - 1, i + 2)], t)


def resample(pts, m=480):
    raw = [poly_eval(pts, k / float(m)) for k in range(m + 1)]
    arc = [0.0]
    for k in range(1, m + 1):
        arc.append(arc[-1] + math.sqrt(sum((raw[k][i] - raw[k - 1][i]) ** 2
                                           for i in range(3))))
    return raw, arc


def at_arc(raw, arc, s):
    if arc[-1] <= 1e-9:
        return raw[0]
    s = max(0.0, min(arc[-1], s))
    lo, hi = 0, len(arc) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if arc[mid] <= s:
            lo = mid
        else:
            hi = mid
    f = (s - arc[lo]) / max(arc[hi] - arc[lo], 1e-12)
    return tuple(raw[lo][i] + (raw[hi][i] - raw[lo][i]) * f for i in range(3))


def build_positions(phases, total_frames):
    pos = [None] * (total_frames + 1)
    seglen = {}
    for name, f0, f1, mode, pts in phases:
        if mode in ('hold', 'hover'):
            for f in range(f0, f1 + 1):
                pos[f] = tuple(pts[0])
            seglen[name] = 0.0
            continue
        raw, arc = resample(pts)
        seglen[name] = arc[-1]
        for f in range(f0, f1 + 1):
            u = (f - f0) / float(max(1, f1 - f0))
            pos[f] = at_arc(raw, arc, trapezoid(u) * arc[-1])
    for f in range(1, total_frames + 1):
        if pos[f] is None:
            pos[f] = pos[f - 1] if f > 1 else tuple(phases[0][4][0])
    return pos, seglen


# ---- 장애물 모델 (건물 박스 + 화염/연기 기둥) --------------------------------
def main_tower_center(sc):
    """화재 연기 기둥의 축 = 대형동 중심. 레이아웃에서 역산한다."""
    px, py = sc["pos"]
    hx, hy = sc["half_extent"]
    foot = sc["foot"][0]
    lay = sc.get("layout", "")
    if lay in ("big+annex_R", "big+small"):
        return (px - hx + foot * 0.5, py)
    if lay == "annex_L+big":
        return (px + hx - foot * 0.5, py)
    if lay == "two_vertical":
        return (px, py + hy - foot * 0.5)
    return (px, py)


def plume_spheres(spec, n, inten, m=14):
    """연기 기둥을 구 스택으로 근사 + 옥상~기둥 밑동의 화염 기둥.

    반경에는 (a) 좌우 흔들림 SMOKE_SWAY (b) 부호를 알 수 없는 X 방향 기울기
    (c) 축 위치 불확실 10 mm 를 모두 더한 보수적 포락선을 쓴다.
    """
    sc = spec["sectors"][str(n)]
    h = float(sc["h"])
    sh = h * (SMOKE_H[0] + SMOKE_H[1] * inten)
    apex = APEX_MEASURED.get(n, h * 1.9)
    z0 = apex - sh
    r1 = SMOKE_R1[0] + SMOKE_R1[1] * inten
    lean_y = SMOKE_LEAN * (h / 0.5) * (1.0 if sc["pos"][1] >= 0.0 else -1.0)
    pad = SMOKE_LEAN * (h / 0.5) * 0.25 + 0.010
    cx, cy = main_tower_center(sc)
    out = []
    for i in range(m + 1):
        t = i / float(m)
        z = z0 + sh * (t ** 0.92)
        r = SMOKE_R0 + (r1 - SMOKE_R0) * (t ** 0.78) + SMOKE_SWAY * t + pad
        out.append((cx, cy + lean_y * (t ** 1.35), z, r))
    roof = h + MAST
    fr = sc["foot"][0] * 0.5 + 0.03
    for i in range(5):
        out.append((cx, cy, roof + (z0 - roof) * i * 0.25, fr))
    return out, dict(axis=(round(cx, 4), round(cy, 4)), z0=round(z0, 4),
                     apex=round(apex, 4), r_top=round(r1 + SMOKE_SWAY + pad, 4),
                     roof=round(roof, 4), lean_y=round(lean_y, 4))


def sector_boxes(spec):
    out = []
    for sn in sorted(spec["sectors"], key=lambda k: int(k)):
        sc = spec["sectors"][sn]
        out.append(("SEC_%02d" % int(sn), sc["pos"][0], sc["pos"][1],
                    sc["half_extent"][0], sc["half_extent"][1],
                    float(sc["h"]) + MAST))
    return out


def clearance(px, py, pz, boxes, plumes, drone_r, drone_h):
    """드론(실린더 r=drone_r, z∈[pz, pz+drone_h])에서 가장 가까운 장애물."""
    best = ("", 9.0)
    for nm, cx, cy, hx, hy, top in boxes:
        dx = max(abs(px - cx) - hx - drone_r, 0.0)
        dy = max(abs(py - cy) - hy - drone_r, 0.0)
        dz = max(0.0, pz - top)
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        if d < best[1]:
            best = (nm, d)
    for nm, spheres in plumes:
        for cx, cy, cz, r in spheres:
            hd = max(0.0, math.hypot(px - cx, py - cy) - drone_r)
            vd = max(0.0, cz - (pz + drone_h), pz - cz)
            d = math.hypot(hd, vd) - r
            if d < best[1]:
                best = (nm, d)
    return best
# ==================================================================
# TRAJECTORY CORE END
# ==================================================================


# ---------------------------------------------------------------- F커브 유틸
def _fcurves_of(id_block):
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


def bake_channel(owner, data_path, index, frames, values,
                 interp='LINEAR', handle='AUTO_CLAMPED'):
    """프레임/값 배열을 F커브에 한 번에 굽는다 (80_motion.py 와 동일 수법)."""
    assert len(frames) == len(values) and len(frames) > 0
    if index is None:
        setattr(owner, data_path, float(values[0]))
        owner.keyframe_insert(data_path, frame=int(frames[0]))
    else:
        getattr(owner, data_path)[index] = float(values[0])
        owner.keyframe_insert(data_path, index=index, frame=int(frames[0]))
    fc = _find_fcurve(owner, data_path, index)
    if fc is None:
        for f, v in zip(frames, values):
            if index is None:
                setattr(owner, data_path, float(v))
                owner.keyframe_insert(data_path, frame=int(f))
            else:
                getattr(owner, data_path)[index] = float(v)
                owner.keyframe_insert(data_path, index=index, frame=int(f))
        return _find_fcurve(owner, data_path, index)
    kps = fc.keyframe_points
    if len(kps) != 1:
        for f, v in zip(frames[1:], values[1:]):
            if index is None:
                setattr(owner, data_path, float(v))
                owner.keyframe_insert(data_path, frame=int(f))
            else:
                getattr(owner, data_path)[index] = float(v)
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
    if fc is None:
        return None
    nm = fc.modifiers.new('NOISE')
    nm.strength = float(strength)
    nm.scale = float(scale)
    nm.phase = float(phase)
    try:
        nm.blend_type = 'ADD'
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


# ================================================================== 빌드 시작
purge("DPATH_")
COL_NAME = "10_Drone"
COL = link_collection(COL_NAME)

scene = bpy.context.scene
scene.render.fps = FPS
scene.render.fps_base = 1.0
scene.frame_start = 1
if scene.frame_end < TOTAL_FRAMES:
    scene.frame_end = TOTAL_FRAMES

root = bpy.data.objects.get("DRN_Root")
if root is None:
    raise RuntimeError(
        "DRN_Root 가 없다. 75_drone.py 를 먼저 실행해야 한다.\n"
        "실행 순서: ... -> 70 -> 75 -> 80 -> 82 -> 90 -> 95")

ROTOR_TAGS = ("FL", "FR", "RL", "RR")
ROTORS = [bpy.data.objects.get("DRN_Rotor_" + t) for t in ROTOR_TAGS]
_missing = [t for t, r in zip(ROTOR_TAGS, ROTORS) if r is None]
if _missing:
    raise RuntimeError("로터 오브젝트 누락: %s — 75_drone.py 를 다시 실행하라" % _missing)

ROTOR_R = float(root.get("rotor_r", 0.026))
FOOT = float(root.get("footprint", 0.172))
DRONE_R = FOOT * 0.5
DRONE_H = float(root.get("height", 0.0642)) + 0.010
FWD = str(root.get("forward_axis", "+X"))
assert FWD == "+X", "드론 전방이 +X 가 아니다 (%s) — 기수 계산을 고쳐야 한다" % FWD
YAW0 = float(root.rotation_euler[2])

# ---------------------------------------------------------------- 1. 궤적
POS, SEGLEN = build_positions(PHASES, TOTAL_FRAMES)

VEL = [(0.0, 0.0, 0.0)] * (TOTAL_FRAMES + 1)
SPD = [0.0] * (TOTAL_FRAMES + 1)
for f in range(2, TOTAL_FRAMES + 1):
    v = tuple((POS[f][i] - POS[f - 1][i]) * FPS for i in range(3))
    VEL[f] = v
    SPD[f] = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
VEL[1] = VEL[2]
SPD[1] = SPD[2]

ACC = [(0.0, 0.0, 0.0)] * (TOTAL_FRAMES + 1)
for f in range(3, TOTAL_FRAMES + 1):
    ACC[f] = tuple((VEL[f][i] - VEL[f - 1][i]) * FPS for i in range(3))


def smooth_seq(a, passes=2):
    n = len(a) - 1
    for _ in range(passes):
        a = [a[0]] + [(a[max(1, i - 1)] + 2.0 * a[i] + a[min(n, i + 1)]) * 0.25
                      for i in range(1, n + 1)]
    return a


AX = smooth_seq([ACC[f][0] for f in range(TOTAL_FRAMES + 1)], 3)
AY = smooth_seq([ACC[f][1] for f in range(TOTAL_FRAMES + 1)], 3)

# ---------------------------------------------------------------- 2. 기수(yaw)
YAW = [YAW0] * (TOTAL_FRAMES + 1)
cur = YAW0
for f in range(1, TOTAL_FRAMES + 1):
    vx, vy = VEL[f][0], VEL[f][1]
    if math.hypot(vx, vy) > YAW_V_MIN:
        tgt = math.atan2(vy, vx)
        while tgt - cur > math.pi:
            tgt -= 2.0 * math.pi
        while tgt - cur < -math.pi:
            tgt += 2.0 * math.pi
        cur = cur + (tgt - cur) * YAW_ALPHA
    YAW[f] = cur

# 착륙 자세 정렬 — 헬리패드에 세워둔 초기 기수로 되돌린다.
_end = YAW[F_YAW_HOME0]
_tgt = YAW0
while _tgt - _end > math.pi:
    _tgt -= 2.0 * math.pi
while _tgt - _end < -math.pi:
    _tgt += 2.0 * math.pi
for f in range(F_YAW_HOME0, TOTAL_FRAMES + 1):
    u = smoothstep((f - F_YAW_HOME0) / float(F_YAW_HOME1 - F_YAW_HOME0))
    YAW[f] = YAW[f] + (_tgt - YAW[f]) * u

# ---------------------------------------------------------------- 3. 기울기
# 쿼드콥터는 추력 벡터를 기울여 이동한다. 가속하면 기수를 숙이고,
# 등속에서도 항력분만큼 숙인 채로 간다. 호버에서는 가속·속도가 0이라 자동으로 0.
PITCH = [0.0] * (TOTAL_FRAMES + 1)
ROLL = [0.0] * (TOTAL_FRAMES + 1)
p_s = r_s = 0.0
for f in range(1, TOTAL_FRAMES + 1):
    c, s = math.cos(YAW[f]), math.sin(YAW[f])
    a_lon = AX[f] * c + AY[f] * s
    a_lat = -AX[f] * s + AY[f] * c
    v_lon = VEL[f][0] * c + VEL[f][1] * s
    v_lat = -VEL[f][0] * s + VEL[f][1] * c
    p_t = TILT_MAX * math.tanh(a_lon / TILT_A_REF + v_lon / TILT_V_REF)
    r_t = -TILT_MAX * math.tanh(a_lat / TILT_A_REF + v_lat / TILT_V_REF)
    p_s += (p_t - p_s) * TILT_ALPHA
    r_s += (r_t - r_s) * TILT_ALPHA
    PITCH[f] = p_s
    ROLL[f] = r_s
PITCH = smooth_seq(PITCH, 2)
ROLL = smooth_seq(ROLL, 2)

# 호버·수직 구간은 기울기 0 이어야 한다 — 1차 지연의 꼬리를 걷어낸다.
# 착륙은 특히 중요하다. 기울어진 채 내려오면 스키드 한쪽부터 닿는 것처럼 보인다.
for f0, f1, ramp in ((F_SHOOT2[0], F_SHOOT2[1], 12.0),
                     (F_SHOOT9[0], F_SHOOT9[1], 12.0),
                     (F_RETURN_END - 14, TOTAL_FRAMES, 20.0),
                     (1, F_TAKEOFF_END, 1.0)):
    for f in range(f0, f1 + 1):
        w = min(1.0, (f - f0) / ramp)
        PITCH[f] *= (1.0 - w)
        ROLL[f] *= (1.0 - w)

TILT_PEAK = max(max(abs(p) for p in PITCH), max(abs(r) for r in ROLL))
HOVER_TILT = max(max(max(abs(PITCH[f]), abs(ROLL[f]))
                     for f in range(f0 + 20, f1 + 1))
                 for f0, f1 in (F_SHOOT2, F_SHOOT9))
LAND_TILT = max(max(abs(PITCH[f]), abs(ROLL[f]))
                for f in range(F_RETURN_END + 20, TOTAL_FRAMES + 1))

# ---------------------------------------------------------------- 4. 로터
THROTTLE = [0.0] * (TOTAL_FRAMES + 1)
for f in range(1, TOTAL_FRAMES + 1):
    if f <= F_SPOOL0:
        t = 0.0
    elif f < F_SPOOL1:
        t = smoothstep((f - F_SPOOL0) / float(F_SPOOL1 - F_SPOOL0))
    elif f <= TOTAL_FRAMES - 12:
        t = 1.0
    else:
        t = 1.0 - smoothstep((f - (TOTAL_FRAMES - 12)) / 12.0)
    THROTTLE[f] = t

OMEGA = [0.0] * (TOTAL_FRAMES + 1)
for f in range(1, TOTAL_FRAMES + 1):
    OMEGA[f] = (OMEGA_IDLE + (OMEGA_FLIGHT - OMEGA_IDLE) * THROTTLE[f]
                + OMEGA_CLIMB * max(0.0, VEL[f][2]))
ROTOR_ANG = [0.0] * (TOTAL_FRAMES + 1)
for f in range(2, TOTAL_FRAMES + 1):
    ROTOR_ANG[f] = ROTOR_ANG[f - 1] + OMEGA[f] / float(FPS)

# ---------------------------------------------------------------- 5. 검산
BOXES = sector_boxes(SPEC)
PLUMES = []
PLUME_INFO = {}
for fb in SPEC.get("fire_buildings", []):
    n = int(fb["sector"])
    sph, info = plume_spheres(SPEC, n, float(fb["intensity"]))
    PLUMES.append(("FIRE_%02d" % n, sph))
    PLUME_INFO["SEC_%02d" % n] = info

CLR = []
for f in range(1, TOTAL_FRAMES + 1):
    x, y, z = POS[f]
    if z < 0.02:                       # 접지 상태는 헬리패드 위라 검사 제외
        CLR.append((f, "GROUND", 9.0))
        continue
    nm, d = clearance(x, y, z, BOXES, PLUMES, DRONE_R, DRONE_H)
    CLR.append((f, nm, d))
CLR_MIN = min(CLR, key=lambda a: a[2])
CLR_BAD = [c for c in CLR if c[2] < CLEAR_REQ]

# 스펙 웨이포인트를 그대로 썼다면 어땠는지 — 고도를 올린 근거를 수치로 남긴다
SPEC_WP_CHECK = []
for wp in DR.get("waypoints", []):
    x, y, z = wp["pos"]
    if z < 0.02:
        continue
    nm, d = clearance(x, y, z, BOXES, PLUMES, DRONE_R, DRONE_H)
    SPEC_WP_CHECK.append({"tag": wp.get("tag"), "pos": [x, y, z],
                          "clearance_m": round(d, 4), "nearest": nm,
                          "ok": bool(d >= CLEAR_REQ)})

assert not CLR_BAD, ("드론이 %d 프레임에서 %.3f m 요구를 못 지킨다: %s"
                     % (len(CLR_BAD), CLEAR_REQ, CLR_BAD[:5]))
_z = [p[2] for p in POS[1:]]
assert min(_z) >= -1e-6, "드론이 지면 아래로 내려간다 (%.4f)" % min(_z)
for f0, f1 in ((1, F_IDLE_END), (F_IDLE_END, F_TAKEOFF_END),
               (F_RETURN_END, TOTAL_FRAMES)):
    for f in range(f0, f1 + 1):
        assert abs(POS[f][0] - HOME[0]) < 1e-6 and abs(POS[f][1] - HOME[1]) < 1e-6, \
            "이륙/착륙 구간 %d 프레임이 수직이 아니다" % f
_hov = max(max(abs(POS[f][i] - POS[f0][i]) for i in range(3))
           for f0, f1 in (F_SHOOT2, F_SHOOT9) for f in range(f0, f1 + 1))
assert _hov < 1e-6, "호버 구간 위치가 고정되어 있지 않다 (%.5f)" % _hov
assert HOVER_TILT < math.radians(0.35), \
    "호버 구간 기울기가 남아 있다 (%.3f°)" % math.degrees(HOVER_TILT)
assert LAND_TILT < math.radians(0.35), \
    "착륙 구간에서 기체가 기울어 있다 (%.3f°)" % math.degrees(LAND_TILT)
assert TILT_PEAK <= TILT_MAX + 1e-6, "기울기가 상한을 넘었다"
assert min(OMEGA[1:]) > 0.0, "로터가 멈추는 프레임이 있다"
_dpf = math.degrees(max(OMEGA[1:]) / FPS)
assert _dpf < OMEGA_DEG_LIMIT, \
    ("로터가 프레임당 %.0f° 돈다 — 블레이드 2장(180° 대칭)이라 프롭이 멈춰 보인다. "
     "OMEGA_FLIGHT/OMEGA_CLIMB 를 낮춰라" % _dpf)

# ---------------------------------------------------------------- 6. 키프레임
if root.animation_data is not None:
    root.animation_data_clear()
for r in ROTORS:
    if r.animation_data is not None:
        r.animation_data_clear()
for c in list(root.constraints):
    root.constraints.remove(c)

frames = list(range(1, TOTAL_FRAMES + 1))
for i in range(3):
    bake_channel(root, "location", i, frames, [POS[f][i] for f in frames],
                 interp='LINEAR')
bake_channel(root, "rotation_euler", 0, frames, [ROLL[f] for f in frames], interp='LINEAR')
bake_channel(root, "rotation_euler", 1, frames, [PITCH[f] for f in frames], interp='LINEAR')
bake_channel(root, "rotation_euler", 2, frames, [YAW[f] for f in frames], interp='LINEAR')

for tag, r in zip(ROTOR_TAGS, ROTORS):
    sd = float(r.get("spin_dir", 1.0))
    assert abs(abs(sd) - 1.0) < 1e-9, "spin_dir 이 ±1 이 아니다 (%s=%s)" % (tag, sd)
    bake_channel(r, "rotation_euler", 2, frames,
                 [sd * ROTOR_ANG[f] for f in frames], interp='LINEAR')

# 호버 표류 ±3 mm + 비행 중 미세 흔들림. 키를 수백 개 더 찍는 것보다 가볍다.
AIR0, AIR1 = F_IDLE_END + 6, TOTAL_FRAMES - 6
for i in range(3):
    fc = _find_fcurve(root, "location", i)
    add_noise_modifier(fc, AIR_JITTER_LOC, 3.0, phase=17.0 * (i + 1),
                       frame_range=(AIR0, AIR1), blend=(18.0, 18.0))
    for k, (f0, f1) in enumerate((F_SHOOT2, F_SHOOT9)):
        add_noise_modifier(fc, HOVER_DRIFT, HOVER_DRIFT_SCALE,
                           phase=7.0 * (i + 1) + 31.0 * k,
                           frame_range=(f0, f1), blend=(10.0, 10.0))
for i in (0, 1):
    fc = _find_fcurve(root, "rotation_euler", i)
    add_noise_modifier(fc, AIR_JITTER_ROT, 2.6, phase=41.0 * (i + 1),
                       frame_range=(AIR0, AIR1), blend=(18.0, 18.0))

# ---------------------------------------------------------------- 7. 경로 커브
cu = bpy.data.curves.new("DPATH_Main_crv", 'CURVE')
cu.dimensions = '3D'
sp = cu.splines.new('POLY')
STRIDE = 4
pts = [POS[f] for f in range(1, TOTAL_FRAMES + 1, STRIDE)] + [POS[TOTAL_FRAMES]]
sp.points.add(len(pts) - 1)
for bp, p in zip(sp.points, pts):
    bp.co = (p[0], p[1], p[2], 1.0)
sp.use_cyclic_u = False
dpath = bpy.data.objects.new("DPATH_Main", cu)
link_to(dpath, COL)
dpath.hide_render = True
dpath["note"] = "드론 비행 경로 시각화 (렌더 제외). 애니메이션은 DRN_Root 키프레임이다"

# ---------------------------------------------------------------- 8. 이벤트
def nearest_frame_3d(q, f0=1, f1=TOTAL_FRAMES):
    bf, bd = f0, 1e9
    for f in range(f0, f1 + 1):
        d = math.sqrt(sum((POS[f][i] - q[i]) ** 2 for i in range(3)))
        if d < bd:
            bd, bf = d, f
    return bf, bd


PHASE_ROWS = []
for name, f0, f1, mode, ppts in PHASES:
    vs = [SPD[f] for f in range(f0, f1 + 1)]
    PHASE_ROWS.append({
        "name": name, "mode": mode,
        "frame_start": int(f0), "frame_end": int(f1),
        "duration_s": round((f1 - f0) / float(FPS), 3),
        "length_m": round(SEGLEN.get(name, 0.0), 4),
        "speed_max_mps": round(max(vs), 3),
        "speed_mean_mps": round(sum(vs) / len(vs), 3),
        "z_range": [round(min(POS[f][2] for f in range(f0, f1 + 1)), 4),
                    round(max(POS[f][2] for f in range(f0, f1 + 1)), 4)],
        "tilt_peak_deg": round(math.degrees(max(
            max(abs(PITCH[f]), abs(ROLL[f])) for f in range(f0, f1 + 1))), 2),
        "clearance_min_m": round(min(CLR[f - 1][2] for f in range(f0, f1 + 1)), 4),
    })

WP_EVENTS = []
_lo = 1
for tag in ("HOME", "TAKEOFF", "FIRE_2_APPROACH", "FIRE_2_SHOOT", "TRANSIT",
            "FIRE_9_SHOOT", "RETURN", "OVER_HOME", "LANDED"):
    q = WP_TAGS[tag]
    if tag == "HOME":
        f, d = 1, 0.0
    elif tag == "LANDED":
        f, d = TOTAL_FRAMES, 0.0
    else:
        f, d = nearest_frame_3d(q, _lo, TOTAL_FRAMES)
    _lo = max(_lo, f)
    nm, cl = clearance(POS[f][0], POS[f][1], max(POS[f][2], 0.02),
                       BOXES, PLUMES, DRONE_R, DRONE_H)
    spec_wp = next((w for w in DR.get("waypoints", []) if w.get("tag") == tag), None)
    WP_EVENTS.append({
        "tag": tag, "frame": int(f), "time_s": round((f - 1) / float(FPS), 3),
        "pos": [round(v, 4) for v in POS[f]],
        "spec_pos": ([round(v, 4) for v in spec_wp["pos"]] if spec_wp else None),
        "delta_from_spec": ([round(POS[f][i] - spec_wp["pos"][i], 4) for i in range(3)]
                            if spec_wp else None),
        "reach_error_m": round(d, 4),
        "speed_mps": round(SPD[f], 3),
        "yaw_deg": round(math.degrees(YAW[f]), 2),
        "clearance_m": round(cl, 4), "nearest": nm,
    })

SHOOT_EVENTS = []
for tag, (f0, f1) in (("FIRE_2_SHOOT", F_SHOOT2), ("FIRE_9_SHOOT", F_SHOOT9)):
    sec = 2 if tag.startswith("FIRE_2") else 9
    info = PLUME_INFO.get("SEC_%02d" % sec, {})
    nm, cl = clearance(POS[f0][0], POS[f0][1], POS[f0][2],
                       BOXES, PLUMES, DRONE_R, DRONE_H)
    ax = info.get("axis", (0.0, 0.0))
    hd = math.hypot(POS[f0][0] - ax[0], POS[f0][1] - ax[1])
    agl = POS[f0][2] - info.get("roof", 0.0)
    SHOOT_EVENTS.append({
        "tag": tag, "sector": sec,
        "frame_start": int(f0), "frame_end": int(f1),
        "time_s": [round((f0 - 1) / float(FPS), 3), round((f1 - 1) / float(FPS), 3)],
        "hover_pos": [round(v, 4) for v in POS[f0]],
        "plume": info,
        "horizontal_offset_from_plume_axis_m": round(hd, 4),
        "height_above_roof_m": round(agl, 4),
        "nadir_cam_off_axis_deg": round(math.degrees(math.atan2(hd, max(agl, 1e-6))), 1),
        "clearance_m": round(cl, 4), "nearest": nm,
        "note": ("나디르 카메라(DRN_Cam) 광축에서 %.0f° 지점에 화재동이 온다. "
                 "화각 %.0f° 이상이면 프레임에 들어온다."
                 % (math.degrees(math.atan2(hd, max(agl, 1e-6))),
                    2.0 * math.degrees(math.atan2(hd, max(agl, 1e-6))) + 12.0)),
    })

# UGV 타임라인과 교차 점검 (있을 때만)
UGV_XCHECK = None
_tl = os.path.join(WORKSPACE, "spec", "timeline.json")
if os.path.exists(_tl):
    try:
        with open(_tl, "r", encoding="utf-8") as fp:
            _t = json.load(fp)
        _busy = []
        for e in _t.get("events", []):
            _busy.append((e["name"], int(e["frame"])))
        for e in _t.get("avoidance_events", []):
            _busy.append((e["name"], int(e["frame_apex"])))
        _conf = []
        for nm_, fr_ in _busy:
            for se in SHOOT_EVENTS:
                if se["frame_start"] <= fr_ <= se["frame_end"]:
                    _conf.append({"ugv_event": nm_, "frame": fr_,
                                  "drone_state": se["tag"]})
        UGV_XCHECK = {
            "timeline_total_frames": _t.get("total_frames"),
            "same_length": _t.get("total_frames") == TOTAL_FRAMES,
            "ugv_events": _busy,
            "overlapping_with_drone_hover": _conf,
            "note": ("드론 호버 구간과 UGV 이벤트가 겹치면 한 컷에 둘 다 담기 어렵다. "
                     "cinematographer 는 이 목록을 보고 컷을 나눈다."),
        }
    except Exception as _e:
        UGV_XCHECK = {"error": str(_e)}

DRONE_TL = {
    "_meta": {
        "name": "MAICON 정찰 드론 비행 타임라인",
        "author": "motion-director",
        "source": "82_drone_motion.py 가 실행 시점에 궤적을 실측해 생성한다. 손으로 고치지 말 것",
        "owner_note": ("UGV 타임라인은 spec/timeline.json (80_motion.py 소유) 이다. "
                       "이 파일은 드론 전용이며 80 과 서로 덮어쓰지 않는다."),
    },
    "fps": FPS,
    "total_frames": TOTAL_FRAMES,
    "drone": {
        "root": "DRN_Root", "cam_anchor": "DRN_Cam",
        "rotors": ["DRN_Rotor_%s" % t for t in ROTOR_TAGS],
        "rotor_spin_dir": {t: float(r.get("spin_dir", 1.0))
                           for t, r in zip(ROTOR_TAGS, ROTORS)},
        "forward_axis": FWD, "footprint_m": FOOT, "rotor_r_m": ROTOR_R,
        "cruise_z_spec_m": CRUISE_Z,
        "cam_note": "DRN_Cam 은 -Z 나디르. 화면 위쪽이 기체 전방(+X)",
    },
    "phases": PHASE_ROWS,
    "waypoints": WP_EVENTS,
    "shoot": SHOOT_EVENTS,
    "attitude": {
        "tilt_max_deg": round(math.degrees(TILT_MAX), 1),
        "tilt_peak_deg": round(math.degrees(TILT_PEAK), 2),
        "hover_tilt_max_deg": round(math.degrees(HOVER_TILT), 3),
        "land_tilt_max_deg": round(math.degrees(LAND_TILT), 3),
        "yaw_mode": "진행 방향 추종 (수평속도 %.3f m/s 이상), 착륙 전 초기 기수 복귀" % YAW_V_MIN,
        "hover_drift_m": HOVER_DRIFT,
    },
    "rotors": {
        "omega_idle_rad_s": OMEGA_IDLE,
        "omega_flight_rad_s": OMEGA_FLIGHT,
        "deg_per_frame_idle": round(math.degrees(OMEGA_IDLE / FPS), 1),
        "deg_per_frame_flight": round(math.degrees(OMEGA_FLIGHT / FPS), 1),
        "total_rev": round(ROTOR_ANG[TOTAL_FRAMES] / (2.0 * math.pi), 2),
        "note": ("블레이드 2장(180° 대칭)이라 프레임당 180° 근처면 프롭이 멈춰 보인다. "
                 "비행 %.0f°/frame 은 그 함정 밖이다. 모션 블러 권장."
                 % math.degrees(OMEGA_FLIGHT / FPS)),
    },
    "qa": {
        "measured": True,
        "clearance_required_m": CLEAR_REQ,
        "clearance_min_m": round(CLR_MIN[2], 4),
        "clearance_min_frame": int(CLR_MIN[0]),
        "clearance_min_obstacle": CLR_MIN[1],
        "frames_below_requirement": len(CLR_BAD),
        "speed_max_mps": round(max(SPD[1:]), 3),
        "climb_rate_max_mps": round(max(abs(VEL[f][2]) for f in range(1, TOTAL_FRAMES + 1)), 3),
        "vertical_takeoff": True, "vertical_landing": True,
        "spec_waypoint_check_at_cruise_z": SPEC_WP_CHECK,
        "altitude_change_reason": (
            "스펙 순항고도 0.62 m 는 SEC_02 연기 기둥(0.579~0.977) 한가운데이고 "
            "최고 건물(0.643) 보다 낮다. 접근·촬영 구간에서 고도를 올려 해결했다."),
        "plumes": PLUME_INFO,
    },
    "ugv_cross_check": UGV_XCHECK,
}

DRONE_TL_PATH = os.path.join(WORKSPACE, "spec", "drone_timeline.json")
with open(DRONE_TL_PATH, "w", encoding="utf-8") as fp:
    json.dump(DRONE_TL, fp, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------- 9. 마무리
scene.frame_set(1)

print("[82_drone] --- 비행 구간 ---")
for r in PHASE_ROWS:
    print("  %-9s f%3d-%3d (%5.2fs) %5.3f m  v %.3f/%.3f  z %.2f~%.2f  "
          "기울기 %.1f°  최소여유 %.4f"
          % (r["name"], r["frame_start"], r["frame_end"], r["duration_s"],
             r["length_m"], r["speed_mean_mps"], r["speed_max_mps"],
             r["z_range"][0], r["z_range"][1], r["tilt_peak_deg"],
             r["clearance_min_m"]))
print("[82_drone] --- 웨이포인트 (스펙 대비) ---")
for e in WP_EVENTS:
    d = e["delta_from_spec"]
    print("  %-16s f%4d (%6.2fs) (%+.3f,%+.3f,%.3f) %s  여유 %.4f [%s]"
          % (e["tag"], e["frame"], e["time_s"], e["pos"][0], e["pos"][1], e["pos"][2],
             ("Δ(%+.2f,%+.2f,%+.2f)" % tuple(d)) if d else "spec 없음",
             e["clearance_m"], e["nearest"]))
print("[82_drone] --- 스펙 순항고도 0.62 로 그대로 갔다면 ---")
for c in SPEC_WP_CHECK:
    print("    %-16s %.4f m [%s] %s"
          % (c["tag"], c["clearance_m"], c["nearest"], "" if c["ok"] else "<-- 0.15 미달"))
print("[82_drone] --- 촬영 호버 ---")
for s in SHOOT_EVENTS:
    print("  %-14s f%d-%d  연기축에서 수평 %.3f m / 옥상 위 %.3f m / 나디르 광축 %.1f°  여유 %.4f"
          % (s["tag"], s["frame_start"], s["frame_end"],
             s["horizontal_offset_from_plume_axis_m"], s["height_above_roof_m"],
             s["nadir_cam_off_axis_deg"], s["clearance_m"]))
print("[82_drone] --- 검산 ---")
print("  최소 클리어런스 %.4f m @f%d [%s] (요구 %.2f, 미달 프레임 %d)"
      % (CLR_MIN[2], CLR_MIN[0], CLR_MIN[1], CLEAR_REQ, len(CLR_BAD)))
print("  최고 속도 %.3f m/s / 최대 상승·하강률 %.3f m/s / 기울기 최대 %.2f° (호버 %.3f°)"
      % (max(SPD[1:]), max(abs(VEL[f][2]) for f in range(1, TOTAL_FRAMES + 1)),
         math.degrees(TILT_PEAK), math.degrees(HOVER_TILT)))
print("  로터 총 %.1f rev / 아이들 %.0f°/frame / 비행 %.0f°/frame / spin_dir %s"
      % (ROTOR_ANG[TOTAL_FRAMES] / (2.0 * math.pi),
         math.degrees(OMEGA_IDLE / FPS), math.degrees(OMEGA_FLIGHT / FPS),
         "/".join("%s%+d" % (t, int(r.get("spin_dir", 1)))
                  for t, r in zip(ROTOR_TAGS, ROTORS))))
if UGV_XCHECK:
    print("  UGV 타임라인 교차 점검: 총 프레임 일치=%s / 드론 호버와 겹치는 UGV 이벤트 %d건 %s"
          % (UGV_XCHECK.get("same_length"),
             len(UGV_XCHECK.get("overlapping_with_drone_hover", [])),
             [c["ugv_event"] for c in UGV_XCHECK.get("overlapping_with_drone_hover", [])]))
else:
    print("  UGV 타임라인 없음 — 80_motion.py 실행 후 82 를 다시 돌리면 교차 점검이 붙는다")

print("[82_drone] DRN_Root 키 %d프레임 x 6채널 + 로터 4개 | DPATH_Main(%d pts) | "
      "drone_timeline.json -> %s"
      % (TOTAL_FRAMES, len(pts),
         os.path.relpath(DRONE_TL_PATH, os.path.dirname(WORKSPACE))))
