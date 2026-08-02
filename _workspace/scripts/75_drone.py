# -*- coding: utf-8 -*-
"""
75_drone.py — UAV 정찰 드론 (asset-modeler 산출)

실행 순서:  ... → 60_markers → 55_placement → 70_vehicle → **75_drone** → 80_motion → ...

실제 본선 과제의 플랫폼은 UGV 단독이 아니라 **UGV + 드론**이다. 과제3(목표추적)은
9개 건물 중 불이 난 2동을 드론과 로봇이 함께 탐지하는 문제이고, 스펙의
drone.waypoints 9개는 헬리패드 이륙 → 화재 섹터 2 촬영 → 섹터 9 촬영 → 복귀
순서를 그대로 담고 있다.

부품 이름은 정확히 지킨다. motion-director 와 cinematographer 가 이 이름으로
부품을 찾으므로, 다르면 애니메이션과 카메라가 **조용히** 실패한다.

    DRN_Root            빈 오브젝트. 모든 부품의 부모. 경로 애니메이션은 여기에만 건다
    DRN_Body            동체 0.11 x 0.11 x 0.035 (팔각 셸 + 캐노피 + 주황 헤딩 표식)
    DRN_Arm_FL/FR/RL/RR 암 4개 (F=+X 전방, L=+Y 좌측 — UGV 와 같은 관례)
    DRN_Rotor_FL/FR/RL/RR  프로펠러 4개. **원점이 로터 중심**이라 로컬 Z 회전으로 돈다
    DRN_Gimbal          하방 짐벌 마운트 (요크 + 포드 + 렌즈)
    DRN_Cam             빈 오브젝트. 하방 카메라 앵커 (-Z 수직 하향)
    DRN_Skid            착륙 스키드 (레일 2 + 다리 4)

--------------------------------------------------------------------------
motion-director 에게 — 프로펠러 돌리는 법
--------------------------------------------------------------------------
로터는 원점이 로터 중심이고 회전축이 이미 **로컬 Z** 다. UGV 바퀴처럼 delta 회전을
쓸 필요가 없다. 그냥 이렇게 쓰면 된다:

    for tag in ("FL", "FR", "RL", "RR"):
        r = bpy.data.objects["DRN_Rotor_%s" % tag]
        r.rotation_euler[2] = r["spin_dir"] * omega * t     # omega = rad/s

spin_dir 은 대각선끼리 같다 (FL=RR=+1, FR=RL=-1). 쿼드콥터의 반토크 상쇄 배치이고,
날개 피치도 그 방향에 맞춰 좌우 대칭으로 꼬아 두었다 — 전부 같은 방향으로 돌리면
프로펠러가 뒤집혀 보인다.

프레임당 회전각이 크면 30fps 에서 스트로브(역회전처럼 보임)가 난다. 그래서 각
로터에 반투명 블러 디스크를 한 장 심어 두었다. 정지 상태에서는 옅게만 보이고,
돌면 회전면이 채워져 "살아 있는" 드론으로 읽힌다.

--------------------------------------------------------------------------
cinematographer 에게 — 하방 카메라
--------------------------------------------------------------------------
DRN_Cam 은 렌즈 바로 앞의 빈 오브젝트다. 로컬 -Z 가 수직 하향(나디르)을 향한다.
로컬 yaw 를 -90° 준 이유는 화면 위쪽이 드론 진행 방향(+X)이 되게 하기 위함이다.
안 그러면 하방 영상의 위쪽이 드론의 왼쪽이라 방향 감각이 어긋난다.

    cam.parent = bpy.data.objects["DRN_Cam"]
    cam.rotation_euler = (0, 0, 0)     # 앵커 회전을 그대로 물려받는다
    cam.data.clip_start = 0.005        # 실측 스케일 — 기본 0.1 m 면 지오메트리가 잘린다

--------------------------------------------------------------------------
스케일 근거
--------------------------------------------------------------------------
UGV 0.20 x 0.13 m, 차선 폭 0.30 m 인 축소 모형이다. 동체 0.11 은 스펙 값이고,
프로펠러까지 포함한 축정렬 풋프린트는 0.172 x 0.172 m 로 UGV 전장(0.20)보다 작다.
헬리패드는 0.50 x 0.44 m 라 착륙 상태로 여유 있게 들어간다.
"""

import bpy
import bmesh
import math
import os

WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
exec(open(os.path.join(WORKSPACE, "scripts", "00_common.py")).read())

# ---------------------------------------------------------------- 치수 (스펙 우선)
DR = SPEC.get("drone", {})
HOME = [float(v) for v in DR.get("home", [-1.95, 0.80, 0.0])]
if len(HOME) < 3:
    HOME = list(HOME) + [0.0] * (3 - len(HOME))
CRUISE_Z = float(DR.get("cruise_z", 0.62))
BODY = [float(v) for v in DR.get("body", [0.11, 0.11, 0.035])]
BW, BD, BH = BODY[0], BODY[1], BODY[2]
WAYPOINTS = DR.get("waypoints", [])

HALF = BW * 0.5              # 0.0550  동체 반폭
CHAMFER = BW * 0.20          # 0.0220  팔각 모서리 컷
SKID_H = 0.0220              # 스키드 높이 = 동체 바닥 z
Z_B0 = SKID_H                # 0.0220  동체 바닥
Z_B1 = Z_B0 + BH             # 0.0570  동체 상면 (= 스펙 body 높이 그대로)

HUB = 0.0600                 # 중심 → 로터 축의 X/Y 성분 (X 배치)
ROTOR_R = 0.0260             # 프로펠러 반경
Z_ARM = 0.0340               # 암 중심 높이 (동체 중간)
Z_ROTOR = 0.0580             # 로터 원점 z — 동체 상면(0.057)보다 위여야 프롭이 안 묻힌다

FOOT = 2.0 * (HUB + ROTOR_R)                              # 0.1720 축정렬 풋프린트
DIAG = 2.0 * (HUB * math.sqrt(2.0) + ROTOR_R)             # 0.2217 대각 프롭 팁 간격
TOP_Z = Z_ROTOR + 0.0062                                  # 0.0642 전고

UGV_LEN = float(SPEC.get("vehicle", {}).get("size", [0.20])[0])
PAD = SPEC.get("helipad", {}).get("size", [0.5, 0.44])


# ---------------------------------------------------------------- 지오메트리 빌더
def geo_new():
    """여러 덩어리를 한 메시로 합치기 위한 누적 버퍼."""
    return {"v": [], "f": [], "mi": [], "sm": []}


def geo_add(g, verts, faces, mi=0, smooth=False):
    off = len(g["v"])
    for p in verts:
        g["v"].append((float(p[0]), float(p[1]), float(p[2])))
    for k, fc in enumerate(faces):
        g["f"].append(tuple(i + off for i in fc))
        g["mi"].append(mi[k] if isinstance(mi, (list, tuple)) else mi)
        g["sm"].append(smooth[k] if isinstance(smooth, (list, tuple)) else smooth)
    return g


def _xf(p, rot, pivot, trans):
    x, y, z = p[0] - pivot[0], p[1] - pivot[1], p[2] - pivot[2]
    rx, ry, rz = rot
    if rx:
        c, s = math.cos(rx), math.sin(rx)
        y, z = y * c - z * s, y * s + z * c
    if ry:
        c, s = math.cos(ry), math.sin(ry)
        x, z = x * c + z * s, -x * s + z * c
    if rz:
        c, s = math.cos(rz), math.sin(rz)
        x, y = x * c - y * s, x * s + y * c
    return (x + pivot[0] + trans[0], y + pivot[1] + trans[1], z + pivot[2] + trans[2])


def geo_merge(g, sub, rot=(0.0, 0.0, 0.0), pivot=(0.0, 0.0, 0.0), trans=(0.0, 0.0, 0.0)):
    off = len(g["v"])
    for p in sub["v"]:
        g["v"].append(_xf(p, rot, pivot, trans))
    for fc, mi, sm in zip(sub["f"], sub["mi"], sub["sm"]):
        g["f"].append(tuple(i + off for i in fc))
        g["mi"].append(mi)
        g["sm"].append(sm)
    return g


def add_box(g, x0, x1, y0, y1, z0, z1, mi=0):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return geo_add(g, v, f, mi=mi)


def add_boxc(g, cx, cy, z0, w, d, h, mi=0):
    return add_box(g, cx - w * 0.5, cx + w * 0.5,
                   cy - d * 0.5, cy + d * 0.5, z0, z0 + h, mi=mi)


def add_cyl(g, base, r, length, axis='Z', seg=16, r_top=None, mi=0, smooth=True):
    rt = r if r_top is None else r_top
    bx, by, bz = base
    v = []
    for k, rr in ((0.0, float(r)), (float(length), float(rt))):
        for i in range(seg):
            a = 2.0 * math.pi * i / seg
            cc, ss = math.cos(a), math.sin(a)
            if axis == 'X':
                v.append((bx + k, by + rr * cc, bz + rr * ss))
            elif axis == 'Y':
                v.append((bx + rr * ss, by + k, bz + rr * cc))
            else:
                v.append((bx + rr * cc, by + rr * ss, bz + k))
    f, sm = [], []
    for i in range(seg):
        j = (i + 1) % seg
        f.append((i, j, seg + j, seg + i))
        sm.append(smooth)
    f.append(tuple(range(seg - 1, -1, -1)))
    sm.append(False)
    f.append(tuple(range(seg, 2 * seg)))
    sm.append(False)
    return geo_add(g, v, f, mi=mi, smooth=sm)


def add_prism_z(g, poly, z0, z1, mi=0):
    """XY 다각형을 Z 방향으로 밀어낸 각기둥 (팔각 셸용)."""
    n = len(poly)
    v = [(p[0], p[1], z0) for p in poly] + [(p[0], p[1], z1) for p in poly]
    f = []
    for i in range(n):
        j = (i + 1) % n
        f.append((i, j, n + j, n + i))
    f.append(tuple(range(n - 1, -1, -1)))
    f.append(tuple(range(n, 2 * n)))
    return geo_add(g, v, f, mi=mi)


def add_strut(g, p0, p1, w, mi=0):
    """두 점을 잇는 사각 단면 기둥 (암·다리)."""
    dx, dy, dz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    L = math.sqrt(dx * dx + dy * dy + dz * dz)
    if L < 1e-9:
        return g
    th = math.acos(max(-1.0, min(1.0, dz / L)))
    ps = math.atan2(dy, dx)
    sub = geo_new()
    add_boxc(sub, 0.0, 0.0, 0.0, w, w, L, mi=mi)
    return geo_merge(g, sub, rot=(0.0, th, ps), pivot=(0.0, 0.0, 0.0), trans=p0)


def add_disc(g, z, r, seg=32, mi=0):
    v = [(r * math.cos(2.0 * math.pi * i / seg),
          r * math.sin(2.0 * math.pi * i / seg), z) for i in range(seg)]
    return geo_add(g, v, [tuple(range(seg))], mi=mi, smooth=False)


def octagon(half, chamfer):
    """정사각형 모서리를 자른 팔각형. 직육면체보다 실루엣이 '기체'처럼 읽힌다."""
    a, b = float(half), float(half) - float(chamfer)
    return [(a, b), (b, a), (-b, a), (-a, b), (-a, -b), (-b, -a), (b, -a), (a, -b)]


def geo_build(name, g, mats, col, loc=(0.0, 0.0, 0.0), bevel=0.0006, segments=2):
    """누적 버퍼를 단일 메시로 굽는다. 면별 머티리얼 인덱스/스무딩까지 적용."""
    ob = mesh_object(name, g["v"], g["f"], loc=loc, col=col)
    me = ob.data
    if len(me.polygons):
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        me.update()
    for m in mats:
        me.materials.append(m)
    if len(me.polygons) == len(g["mi"]):
        top = max(0, len(mats) - 1)
        for p, mi, sm in zip(me.polygons, g["mi"], g["sm"]):
            p.material_index = min(int(mi), top)
            p.use_smooth = bool(sm)
    if bevel:
        add_bevel(ob, width=bevel, segments=segments)
    return ob


def _try_set(obj, attr, value):
    """버전마다 있고 없는 프로퍼티를 조용히 건너뛴다."""
    if obj is None or not hasattr(obj, attr):
        return False
    try:
        setattr(obj, attr, value)
        return True
    except (AttributeError, TypeError, ValueError):
        return False


# ---------------------------------------------------------------- 머티리얼
M_SHELL = get_or_create_material("DRN_Shell", color=[0.70, 0.71, 0.72], roughness=0.42)
M_DARK = get_or_create_material("DRN_Dark", color=[0.055, 0.055, 0.062], roughness=0.58)
M_ACCENT = get_or_create_material("DRN_Accent", color=[0.90, 0.36, 0.04], roughness=0.40)
M_METAL = get_or_create_material("DRN_Metal", color=[0.44, 0.45, 0.47],
                                 roughness=0.34, metallic=0.80)
M_BLADE = get_or_create_material("DRN_Blade", color=[0.085, 0.088, 0.095], roughness=0.34)
M_LENS = get_or_create_material("DRN_Lens", color=[0.02, 0.03, 0.05], roughness=0.08,
                                metallic=0.30, emission=[0.10, 0.45, 0.75],
                                emission_strength=1.1)
M_NAV_G = get_or_create_material("DRN_NavGreen", color=[0.05, 0.35, 0.10], roughness=0.25,
                                 emission=[0.10, 1.0, 0.20], emission_strength=6.0)
M_NAV_R = get_or_create_material("DRN_NavRed", color=[0.35, 0.04, 0.04], roughness=0.25,
                                 emission=[1.0, 0.10, 0.06], emission_strength=6.0)

# 프롭 블러 디스크. 반투명이라 정지 화면에서는 옅은 원반, 회전 시에는 회전면으로 읽힌다.
M_DISC = get_or_create_material("DRN_RotorDisc", color=[0.30, 0.31, 0.33], roughness=0.9)
_bsdf = None
for _nd in M_DISC.node_tree.nodes:
    if _nd.type == 'BSDF_PRINCIPLED':
        _bsdf = _nd
        break
if _bsdf is not None:
    _set_input(_bsdf, "Alpha", 0.10)
    _set_input(_bsdf, "Specular IOR Level", 0.05)   # 4.x
    _set_input(_bsdf, "Specular", 0.05)             # 3.x
_try_set(M_DISC, "blend_method", 'BLEND')                # 4.1 이하
_try_set(M_DISC, "shadow_method", 'NONE')
_try_set(M_DISC, "show_transparent_back", False)
_try_set(M_DISC, "surface_render_method", 'BLENDED')     # 4.2+ EEVEE Next
_try_set(M_DISC, "use_transparent_shadow", False)
M_DISC.diffuse_color = (0.30, 0.31, 0.33, 0.10)

BODY_MATS = [M_SHELL, M_DARK, M_ACCENT, M_METAL, M_LENS]
ARM_MATS = [M_DARK, M_METAL, M_ACCENT, M_NAV_G, M_NAV_R]
ROTOR_MATS = [M_BLADE, M_METAL, M_DISC]
GIMBAL_MATS = [M_DARK, M_METAL, M_LENS]
SKID_MATS = [M_DARK, M_METAL, M_ACCENT]


# ---------------------------------------------------------------- 동체
def body_geo():
    """팔각 셸 + 캐노피 + 주황 헤딩 표식. 원점은 DRN_Root (노면 z=0, 기체 중심)."""
    g = geo_new()
    belly = octagon(HALF * 0.95, CHAMFER * 0.90)
    shell = octagon(HALF, CHAMFER)
    band = octagon(HALF * 1.022, CHAMFER * 1.022)
    canopy = octagon(HALF * 0.80, CHAMFER * 0.80)
    cap = octagon(HALF * 0.55, CHAMFER * 0.55)

    add_prism_z(g, belly, Z_B0, Z_B0 + 0.0090, mi=1)              # 배터리 베이(어둡게)
    add_prism_z(g, shell, Z_B0 + 0.0090, Z_B0 + 0.0250, mi=0)     # 메인 셸
    add_prism_z(g, band, Z_B0 + 0.0160, Z_B0 + 0.0200, mi=2)      # 주황 아이덴티티 밴드
    add_prism_z(g, canopy, Z_B0 + 0.0250, Z_B1, mi=0)             # 캐노피 (= 상면 0.057)
    add_prism_z(g, cap, Z_B1, Z_B1 + 0.0015, mi=1)

    # GPS 퍽 — 상면 실루엣에 점 하나가 있으면 오비탈 샷에서 기체 방향이 읽힌다
    add_cyl(g, (-0.006, 0.0, Z_B1 + 0.0015), 0.0080, 0.0020, seg=16, mi=1, smooth=True)
    add_cyl(g, (-0.006, 0.0, Z_B1 + 0.0035), 0.0084, 0.0006, seg=16, mi=2, smooth=True)

    # 전방 노즈 — 동체 앞으로 2.5 mm 돌출한 주황 블록. 헤딩을 옆에서도 읽게 한다
    add_box(g, HALF - 0.006, HALF + 0.0025, -0.010, 0.010,
            Z_B0 + 0.0110, Z_B0 + 0.0210, mi=2)
    # 상면 헤딩 셰브론
    add_box(g, 0.016, 0.038, -0.0050, 0.0050, Z_B1 + 0.0015, Z_B1 + 0.0030, mi=2)

    # 전방 감시 카메라 (짐벌과 별개인 고정 렌즈) + 상태 LED
    add_cyl(g, (HALF - 0.008, 0.0, Z_B0 + 0.0060), 0.0042, 0.0035,
            axis='X', seg=12, mi=3, smooth=True)
    add_cyl(g, (HALF - 0.0046, 0.0, Z_B0 + 0.0060), 0.0032, 0.0008,
            axis='X', seg=12, mi=4, smooth=True)
    add_boxc(g, -HALF + 0.010, 0.0, Z_B1 + 0.0015, 0.008, 0.005, 0.0012, mi=4)

    # 방열 그릴 — 셸 옆면에 얇은 홈을 넣어 평평한 면을 깬다
    for k in range(3):
        yv = -0.014 + k * 0.014
        add_box(g, -HALF - 0.0008, -HALF + 0.0060, yv - 0.0018, yv + 0.0018,
                Z_B0 + 0.0120, Z_B0 + 0.0210, mi=1)
    return g


# ---------------------------------------------------------------- 암 (4개)
def arm_geo(sx, sy, nav_mi):
    """동체에서 로터 축까지의 붐 + 모터 스테이터 + 항법등. loc=(0,0,0), 루트 좌표계."""
    g = geo_new()
    hx, hy = sx * HUB, sy * HUB
    add_strut(g, (sx * 0.024, sy * 0.024, Z_ARM), (hx, hy, Z_ARM), 0.0085, mi=0)
    add_strut(g, (sx * 0.040, sy * 0.026, Z_ARM - 0.0010),
              (sx * 0.030, sy * 0.044, Z_ARM - 0.0010), 0.0040, mi=0)   # 보강 브레이스

    add_cyl(g, (hx, hy, Z_ARM - 0.0055), 0.0098, 0.0022, seg=16, mi=0, smooth=True)
    add_cyl(g, (hx, hy, Z_ARM - 0.0033), 0.0072, Z_ROTOR - (Z_ARM - 0.0033),
            seg=16, mi=1, smooth=True)                                  # 모터 캔
    add_cyl(g, (hx, hy, Z_ARM + 0.0090), 0.0076, 0.0012, seg=16, mi=2, smooth=True)

    # 항법등 — 앞 초록 / 뒤 빨강. 오비탈 샷에서 기체 진행 방향이 즉시 읽힌다
    add_boxc(g, hx, hy, Z_ARM - 0.0105, 0.0070, 0.0070, 0.0050, mi=nav_mi)
    return g


# ---------------------------------------------------------------- 로터 (4개)
def add_blade(g, a0, sign, zc, mi=0):
    """반경을 따라 코드와 피치가 변하는 프로펠러 날개 1장.

    sign 이 회전 방향(spin_dir)이다. 피치 부호를 뒤집어 CW/CCW 프롭을 좌우 대칭으로
    만든다 — 넷을 같은 모양으로 두면 회전시켰을 때 두 개가 거꾸로 도는 것처럼 보인다.
    """
    st = [(0.0058, 0.0058, 0.42), (0.0110, 0.0098, 0.33), (0.0170, 0.0104, 0.24),
          (0.0225, 0.0082, 0.17), (ROTOR_R, 0.0030, 0.12)]
    th = 0.00045
    ca, sa = math.cos(a0), math.sin(a0)
    tx, ty = -sa, ca                       # 접선 방향 = 코드 방향의 기준
    v, f = [], []
    for rr, c, pit in st:
        p = pit * sign
        cx, cy = ca * rr, sa * rr
        hc = c * 0.5
        cp, sp = math.cos(p), math.sin(p)
        chx, chy, chz = tx * cp, ty * cp, sp          # 코드(단위벡터)
        nx, ny, nz = -tx * sp, -ty * sp, cp           # 코드에 수직인 두께 방향
        for s_c, s_n in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            v.append((cx + chx * hc * s_c + nx * th * s_n,
                      cy + chy * hc * s_c + ny * th * s_n,
                      zc + chz * hc * s_c + nz * th * s_n))
    n = len(st)
    for b in range(n - 1):
        s0, s1 = b * 4, (b + 1) * 4
        for k in range(4):
            k2 = (k + 1) % 4
            f.append((s0 + k, s0 + k2, s1 + k2, s1 + k))
    f.append((0, 1, 2, 3))                                              # 뿌리 캡
    f.append(((n - 1) * 4 + 3, (n - 1) * 4 + 2, (n - 1) * 4 + 1, (n - 1) * 4))
    return geo_add(g, v, f, mi=mi, smooth=False)


def rotor_geo(sign):
    """원점 = 로터 중심. 회전축이 이미 로컬 Z 라 delta 회전이 필요 없다."""
    g = geo_new()
    add_cyl(g, (0.0, 0.0, 0.0), 0.0072, 0.0040, seg=16, mi=1, smooth=True)      # 벨
    add_cyl(g, (0.0, 0.0, 0.0040), 0.0050, 0.0022, seg=12, mi=1, smooth=True)   # 허브 캡
    add_blade(g, 0.0, sign, 0.0043, mi=0)
    add_blade(g, math.pi, sign, 0.0043, mi=0)
    add_disc(g, 0.0039, ROTOR_R * 0.97, seg=32, mi=2)                           # 블러 디스크
    return g


# ---------------------------------------------------------------- 짐벌 / 스키드
def gimbal_geo():
    """동체 아래로 내려온 2축 짐벌. 렌즈 바닥이 지면에서 3.6 mm — 스키드(22 mm)가 지켜준다."""
    g = geo_new()
    add_boxc(g, 0.012, 0.0, Z_B0 - 0.0050, 0.030, 0.028, 0.0050, mi=0)      # 요크 플레이트
    for sy in (-1.0, 1.0):
        add_box(g, 0.0040, 0.0200, sy * 0.0115 - 0.0020, sy * 0.0115 + 0.0020,
                0.0090, 0.0175, mi=1)                                        # 요크 암
    add_cyl(g, (0.012, -0.0080, 0.0130), 0.0075, 0.0160, axis='Y', seg=16,
            mi=0, smooth=True)                                               # 카메라 포드
    add_cyl(g, (0.012, 0.0, 0.0040), 0.0050, 0.0060, seg=16, mi=1, smooth=True)  # 렌즈 배럴
    add_cyl(g, (0.012, 0.0, 0.0036), 0.0042, 0.0006, seg=16, mi=2, smooth=True)  # 렌즈 유리
    return g


def skid_geo():
    """레일 2개 + 벌어진 다리 4개. 착륙 상태에서 기체가 땅에 붙어 보이게 하는 부품."""
    g = geo_new()
    for sy in (-1.0, 1.0):
        y = sy * 0.038
        add_box(g, -0.044, 0.044, y - 0.0030, y + 0.0030, 0.0000, 0.0045, mi=0)
        for sx in (-1.0, 1.0):                                   # 레일 끝 들림(스키 코)
            add_box(g, sx * 0.044, sx * 0.052, y - 0.0026, y + 0.0026,
                    0.0022, 0.0060, mi=0)
        for sx in (-1.0, 1.0):                                   # 다리 (바깥으로 벌어짐)
            add_strut(g, (sx * 0.030, sy * 0.028, Z_B0 + 0.0010),
                      (sx * 0.038, y, 0.0045), 0.0050, mi=1)
    add_box(g, -0.0025, 0.0025, -0.038, 0.038, 0.0180, 0.0215, mi=1)   # 가로 브레이스
    for sy in (-1.0, 1.0):                                             # 접지 패드
        add_boxc(g, 0.0, sy * 0.038, 0.0000, 0.030, 0.0080, 0.0012, mi=2)
    return g


# ---------------------------------------------------------------- 빌드
purge("DRN_")

COL_NAME = "10_Drone"
COL = link_collection(COL_NAME)
if COL_NAME not in COLLECTIONS:          # 00_common 의 계층 목록에 등록 (85_environment 와 동일 수법)
    COLLECTIONS.append(COL_NAME)
    PREFIX_OF[COL_NAME] = "DRN_"

# 초기 헤딩 — home 을 벗어나는 첫 웨이포인트를 바라본다. motion-director 가 덮어쓴다.
yaw0 = 0.0
for wp in WAYPOINTS:
    p = wp.get("pos", [])
    if len(p) >= 2 and math.hypot(p[0] - HOME[0], p[1] - HOME[1]) > 1e-4:
        yaw0 = math.atan2(p[1] - HOME[1], p[0] - HOME[0])
        break

root = bpy.data.objects.new("DRN_Root", None)
root.empty_display_type = 'PLAIN_AXES'
root.empty_display_size = 0.05
link_to(root, COL)
root.location = (HOME[0], HOME[1], HOME[2])
root.rotation_euler = (0.0, 0.0, yaw0)
root["rotor_r"] = ROTOR_R
root["cruise_z"] = CRUISE_Z
root["body_size"] = [BW, BD, BH]
root["home"] = [HOME[0], HOME[1], HOME[2]]
root["hub_offset"] = HUB
root["rotor_z"] = Z_ROTOR
root["footprint"] = FOOT
root["diag_span"] = DIAG
root["height"] = TOP_Z
root["forward_axis"] = "+X"
root["waypoints"] = len(WAYPOINTS)
root["note"] = "animate DRN_Root only; spin rotors via rotation_euler[2] * spin_dir"

body = geo_build("DRN_Body", body_geo(), BODY_MATS, COL, loc=(0.0, 0.0, 0.0),
                 bevel=0.0006, segments=2)
gimbal = geo_build("DRN_Gimbal", gimbal_geo(), GIMBAL_MATS, COL, loc=(0.0, 0.0, 0.0),
                   bevel=0.0004, segments=2)
skid = geo_build("DRN_Skid", skid_geo(), SKID_MATS, COL, loc=(0.0, 0.0, 0.0),
                 bevel=0.0004, segments=2)

# F=+X 전방, L=+Y 좌측 (UGV 와 동일 관례).
# spin_dir 은 대각선끼리 같다 — 쿼드콥터의 반토크 상쇄 배치.
CORNERS = (("FL", 1.0, 1.0, 1), ("FR", 1.0, -1.0, -1),
           ("RL", -1.0, 1.0, -1), ("RR", -1.0, -1.0, 1))

arms, rotors = [], []
for tag, sx, sy, spin in CORNERS:
    nav_mi = 3 if sx > 0 else 4                      # 앞=초록 / 뒤=빨강
    a = geo_build("DRN_Arm_%s" % tag, arm_geo(sx, sy, nav_mi), ARM_MATS, COL,
                  loc=(0.0, 0.0, 0.0), bevel=0.0004, segments=2)
    a["corner"] = tag
    arms.append(a)

    r = geo_build("DRN_Rotor_%s" % tag, rotor_geo(spin), ROTOR_MATS, COL,
                  loc=(sx * HUB, sy * HUB, Z_ROTOR), bevel=0.0002, segments=1)
    r.rotation_euler = (0.0, 0.0, 0.0)               # delta 회전 불필요 — 축이 이미 로컬 Z
    r["spin_dir"] = spin
    r["spin_axis"] = "Z"
    r["rotor_r"] = ROTOR_R
    r["corner"] = tag
    _try_set(r, "visible_shadow", False)             # 얇은 날개 그림자는 노이즈로만 보인다
    rotors.append(r)

root["spin_dir"] = [c[3] for c in CORNERS]
root["rotor_order"] = "FL,FR,RL,RR"

# 하방 카메라 앵커. -Z 가 나디르, 로컬 yaw -90° 로 화면 위쪽 = 기체 전방(+X).
cam = bpy.data.objects.new("DRN_Cam", None)
cam.empty_display_type = 'ARROWS'
cam.empty_display_size = 0.025
link_to(cam, COL)
cam.location = (0.012, 0.0, 0.0036)
cam.rotation_euler = (0.0, 0.0, -math.pi * 0.5)
cam["look_axis"] = "-Z"
cam["image_up"] = "+X"
cam["height_m"] = 0.0036
cam["note"] = "nadir: camera -Z points straight down; local yaw -90deg puts drone forward at image top; clip_start <= 0.005"

for ob in [body, gimbal, skid, cam] + arms + rotors:
    ob.parent = root          # matrix_parent_inverse 는 단위행렬 그대로 둔다


# ---------------------------------------------------------------- 검산 출력
NAMES = (["DRN_Root", "DRN_Body", "DRN_Gimbal", "DRN_Cam", "DRN_Skid"]
         + ["DRN_Arm_%s" % c[0] for c in CORNERS]
         + ["DRN_Rotor_%s" % c[0] for c in CORNERS])
missing = [n for n in NAMES if n not in bpy.data.objects]

_zs = []
for ob in [body, gimbal, skid] + arms:
    _zs += [v.co.z for v in ob.data.vertices]
low = min(_zs) if _zs else 0.0

_bad_spin = [c[0] for c in CORNERS
             if bpy.data.objects["DRN_Rotor_%s" % c[0]]["spin_dir"] != c[3]]
_diag_ok = (bpy.data.objects["DRN_Rotor_FL"]["spin_dir"]
            == bpy.data.objects["DRN_Rotor_RR"]["spin_dir"]
            and bpy.data.objects["DRN_Rotor_FR"]["spin_dir"]
            == bpy.data.objects["DRN_Rotor_RL"]["spin_dir"]
            and bpy.data.objects["DRN_Rotor_FL"]["spin_dir"]
            != bpy.data.objects["DRN_Rotor_FR"]["spin_dir"])

print("  치수  동체 %.3f x %.3f x %.3f (스펙 그대로) | 프롭 풋프린트 %.3f x %.3f | "
      "대각 스팬 %.3f | 전고 %.3f"
      % (BW, BD, BH, FOOT, FOOT, DIAG, TOP_Z))
print("  대비  UGV 전장 %.3f 대비 풋프린트 %.0f%% / 동체 %.0f%%  →  드론이 더 작다: %s"
      % (UGV_LEN, FOOT / UGV_LEN * 100.0, BW / UGV_LEN * 100.0,
         "OK" if BW < UGV_LEN and FOOT < UGV_LEN else "VIOLATION"))
print("  로터  r=%.3f  축 오프셋 (%+.3f, %+.3f)  회전면 z=%.3f (동체 상면 %.3f 위 %.1fmm) | "
      "spin_dir FL/FR/RL/RR = %s (대각 동일: %s)"
      % (ROTOR_R, HUB, HUB, Z_ROTOR, Z_B1, (Z_ROTOR - Z_B1) * 1000.0,
         "/".join("%+d" % c[3] for c in CORNERS), "OK" if _diag_ok else "FAIL"))
print("  접지  스키드 바닥 z=%.4f  최저 정점 z=%.4f  짐벌 렌즈 z=%.4f (지면 여유 %.1fmm)"
      % (0.0, low, 0.0036, 0.0036 * 1000.0))
print("  카메라 DRN_Cam @ (%.3f, 0, %.4f)  -Z 수직 하향 / 화면 위 = 기체 전방(+X)"
      % (0.012, 0.0036))
print("  배치  DRN_Root @ (%.2f, %.2f, %.2f) yaw=%.4f rad | 헬리패드 %.2f x %.2f 에 여유 %.0fmm | "
      "cruise_z=%.2f, 웨이포인트 %d개"
      % (HOME[0], HOME[1], HOME[2], yaw0, PAD[0], PAD[1],
         (min(PAD) - FOOT) * 0.5 * 1000.0, CRUISE_Z, len(WAYPOINTS)))

print("[75_drone] built %d objects in %s | parts=%s | missing=%s | spin_dir 오류=%s"
      % (len(COL.objects), COL_NAME,
         "/".join(n.replace("DRN_", "") for n in NAMES),
         missing if missing else "none", _bad_spin if _bad_spin else "none"))
