# -*- coding: utf-8 -*-
"""
70_vehicle.py — UGV 지상 무인차량 (asset-modeler 산출)

부품 이름은 정확히 지킨다. motion-director 와 cinematographer 가 이 이름으로
부품을 찾으므로, 다르면 애니메이션과 카메라가 **조용히** 실패한다.

    UGV_Root        빈 오브젝트. 모든 부품의 부모. 경로 애니메이션은 이것에만 건다
    UGV_Body        차체 (경사 전면 + 펜더 + 카메라 하우징 + 안테나)
    UGV_Wheel_FL    좌전륜   (F=+X 전방, L=+Y 좌측)
    UGV_Wheel_FR    우전륜
    UGV_Wheel_RL    좌후륜
    UGV_Wheel_RR    우후륜
    UGV_Sensor      상단 LiDAR 마운트
    UGV_Cam         전방 카메라 앵커 (빈 오브젝트). 1인칭 샷 카메라가 여기 붙는다

--------------------------------------------------------------------------
motion-director 에게 — 바퀴 굴리는 법
--------------------------------------------------------------------------
바퀴 메시의 축은 **로컬 X** 다. 축을 월드 Y(횡방향)로 세우는 90° 회전은
rotation_euler 가 아니라 **delta_rotation_euler** 에 넣어 두었다. 블렌더는
최종 회전을 R = R_delta @ R_local 로 계산하므로, 로컬 X 회전이 먼저 적용되어
바퀴 자신의 축으로 돈다. 따라서 그냥 이렇게 쓰면 된다:

    w.rotation_euler[0] = dist / wheel_r          # +X 로 전진 = + 부호
    # 또는 통째로 덮어써도 안전하다: w.rotation_euler = (roll, 0, 0)

delta 를 쓴 이유가 이것이다. rotation_euler.z 에 90° 를 넣어 두면 굴림 코드가
z 성분을 덮어쓰는 순간 바퀴가 옆으로 눕는다.

차체·센서는 UGV_Root 원점(노면 z=0, 차량 중심)을 그대로 쓰는 로컬 좌표로
만들어져 있고 location 이 (0,0,0) 이다. 바퀴만 예외로 원점이 바퀴 중심이다 —
그래야 축 회전으로 구른다.
"""

import bpy
import bmesh
import math
import os

WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
exec(open(os.path.join(WORKSPACE, "scripts", "00_common.py")).read())

# ---------------------------------------------------------------- 치수 (스펙 우선)
VS = SPEC.get("vehicle", {})
LEN = float(VS.get("size", [0.20, 0.13, 0.09])[0])
WID = float(VS.get("size", [0.20, 0.13, 0.09])[1])
HGT = float(VS.get("size", [0.20, 0.13, 0.09])[2])
WR = float(VS.get("wheel_r", 0.022))          # 바퀴 반지름
WW = float(VS.get("wheel_w", 0.018))          # 바퀴 폭
HALF_W = float(VS.get("half_w", WID * 0.5))   # 차폭 절반 — 차선 0.30 의 절반보다 좁아야 한다
CAM_Z = float(VS.get("cam_z", 0.07))
CAM_PITCH = float(VS.get("cam_pitch_deg", -8.0))

HX = LEN * 0.5                                 # 0.100  차체 앞뒤 끝
WHEEL_CY = HALF_W - WW * 0.5                   # 0.056  바퀴 중심 Y
WHEEL_CX = 0.062                               # 휠베이스 0.124
HULL_HY = WHEEL_CY - WW * 0.5 - 0.002           # 0.045  차체 반폭 (바퀴와 2 mm 간격)
LANE_W = float(SPEC["road"]["lane_w"])


# ---------------------------------------------------------------- 지오메트리 빌더
def geo_new():
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


def add_prism_xz(g, profile, y0, y1, mi=0):
    n = len(profile)
    v = [(p[0], y0, p[1]) for p in profile] + [(p[0], y1, p[1]) for p in profile]
    f = []
    for i in range(n):
        j = (i + 1) % n
        f.append((i, j, n + j, n + i))
    f.append(tuple(range(n - 1, -1, -1)))
    f.append(tuple(range(n, 2 * n)))
    return geo_add(g, v, f, mi=mi)


def geo_build(name, g, mats, col, loc=(0.0, 0.0, 0.0), bevel=0.0008, segments=2):
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


# ---------------------------------------------------------------- 머티리얼
M_HULL = get_or_create_material("UGV_Hull", color=[0.20, 0.22, 0.19], roughness=0.55)
M_DARK = get_or_create_material("UGV_Dark", color=[0.055, 0.055, 0.062], roughness=0.68)
M_ACCENT = get_or_create_material("UGV_Accent", color=[0.85, 0.34, 0.05], roughness=0.42)
M_LENS = get_or_create_material("UGV_Lens", color=[0.02, 0.03, 0.05], roughness=0.08,
                                metallic=0.30, emission=[0.10, 0.45, 0.75],
                                emission_strength=0.9)
M_LAMP = get_or_create_material("UGV_Lamp", color=[0.95, 0.93, 0.82], roughness=0.20,
                                emission=[1.0, 0.95, 0.80], emission_strength=4.0)
M_TAIL = get_or_create_material("UGV_Tail", color=[0.55, 0.06, 0.05], roughness=0.30,
                                emission=[0.9, 0.08, 0.06], emission_strength=1.6)
M_METAL = get_or_create_material("UGV_Metal", color=[0.42, 0.43, 0.45],
                                 roughness=0.36, metallic=0.80)
M_TIRE = get_or_create_material("UGV_Tire", color=[0.042, 0.042, 0.048], roughness=0.90)
M_HUB = get_or_create_material("UGV_Hub", color=[0.52, 0.53, 0.55],
                               roughness=0.34, metallic=0.80)

BODY_MATS = [M_HULL, M_DARK, M_ACCENT, M_LENS, M_LAMP, M_TAIL, M_METAL]
SENSOR_MATS = [M_METAL, M_LENS, M_DARK]
WHEEL_MATS = [M_TIRE, M_HUB]


# ---------------------------------------------------------------- 차체
def body_geo():
    g = geo_new()
    # 측면 단면: 바닥 z=0.020(지상고), 전면은 경사 글라시, 상면 z=0.064
    hull = [(-HX + 0.002, 0.020), (0.062, 0.020), (HX - 0.002, 0.034),
            (HX - 0.002, 0.052), (0.070, 0.064), (-HX + 0.002, 0.064)]
    add_prism_xz(g, hull, -HULL_HY, HULL_HY, mi=0)
    add_boxc(g, 0.0, 0.0, 0.014, 0.150, 0.072, 0.008, mi=1)          # 스키드 플레이트

    for sy in (-1.0, 1.0):
        y0, y1 = sorted((sy * 0.043, sy * HALF_W))
        for wx in (WHEEL_CX, -WHEEL_CX):                             # 펜더
            add_box(g, wx - 0.028, wx + 0.028, y0, y1, 0.048, 0.056, mi=1)
        a, b = sorted((sy * HULL_HY, sy * (HULL_HY + 0.0014)))
        add_box(g, -0.088, 0.088, a, b, 0.056, 0.060, mi=2)          # 주황 아이덴티티 밴드

    # 전방 카메라 하우징 — UGV_Cam 이 여기서 시작한다
    add_boxc(g, 0.078, 0.0, 0.062, 0.026, 0.032, 0.014, mi=1)
    add_cyl(g, (0.090, 0.0, 0.069), 0.0055, 0.004, axis='X', seg=16, mi=3, smooth=True)

    for sy in (-1.0, 1.0):
        add_boxc(g, HX - 0.006, sy * 0.028, 0.040, 0.008, 0.012, 0.008, mi=4)   # 전조등
        add_boxc(g, -HX + 0.006, sy * 0.030, 0.040, 0.008, 0.012, 0.008, mi=5)  # 후미등
    add_boxc(g, -0.070, 0.0, 0.064, 0.050, 0.072, 0.005, mi=1)       # 후방 적재 랙
    add_boxc(g, -0.070, 0.0, 0.069, 0.020, 0.020, 0.004, mi=6)
    add_cyl(g, (-0.086, 0.032, 0.064), 0.0011, 0.024, seg=8, mi=1, smooth=True)  # 안테나
    add_cyl(g, (-0.086, 0.032, 0.088), 0.0022, 0.002, seg=8, mi=2, smooth=True)
    for sy in (-1.0, 1.0):                                            # 견인 고리
        add_boxc(g, HX - 0.006, sy * 0.014, 0.024, 0.010, 0.006, 0.005, mi=6)
    return g


# ---------------------------------------------------------------- 센서 마운트
def sensor_geo():
    g = geo_new()
    add_boxc(g, -0.030, 0.0, 0.064, 0.032, 0.032, 0.006, mi=0)                    # 페데스탈
    add_cyl(g, (-0.030, 0.0, 0.070), 0.0130, 0.006, seg=20, mi=0, smooth=True)
    add_cyl(g, (-0.030, 0.0, 0.076), 0.0136, 0.008, seg=20, mi=1, smooth=True)    # 회전 유리창
    add_cyl(g, (-0.030, 0.0, 0.084), 0.0130, 0.004, seg=20, mi=0, smooth=True)
    add_cyl(g, (-0.030, 0.0, 0.088), 0.0040, 0.002, seg=12, mi=2, smooth=True)
    return g


# ---------------------------------------------------------------- 바퀴 (축 = 로컬 X)
def wheel_geo():
    """축은 로컬 X, 원점은 바퀴 중심.

    최대 반지름은 정확히 WR 이어야 한다 — 러그를 WR 바깥으로 내밀면 접지면이
    노면 아래로 파고든다. 그래서 카커스를 WR-1.6 mm 로 깎고 러그가 WR 까지
    채우게 만든다. 폭도 WW 를 넘지 않아야 전폭이 차선 안에 남는다.
    """
    g = geo_new()
    hw = WW * 0.5                 # 0.009
    tw = hw - 0.002               # 타이어 반폭 0.007, 나머지 2 mm 는 휠 림
    add_cyl(g, (-tw, 0.0, 0.0), WR - 0.0016, tw * 2.0, axis='X', seg=28,
            mi=0, smooth=True)
    for sx in (-1.0, 1.0):        # 좌우 대칭 — 한 메시를 네 바퀴가 공유한다
        b0 = tw if sx > 0 else -(tw + 0.0012)      # 타이어 옆면에 딱 붙인다
        b1 = tw + 0.0012 if sx > 0 else -hw        # (틈이 생기면 조각이 뜬다)
        add_cyl(g, (b0, 0.0, 0.0), WR * 0.60, 0.0012, axis='X', seg=18,
                mi=1, smooth=True)
        add_cyl(g, (b1, 0.0, 0.0), WR * 0.28, 0.0008, axis='X', seg=12,
                mi=1, smooth=True)
    for k in range(14):           # 트레드 러그 — 굴러가는 게 눈에 보인다
        lug = geo_new()
        add_box(lug, -tw * 0.85, tw * 0.85, -0.0020, 0.0020,
                WR - 0.0030, WR, mi=0)
        geo_merge(g, lug, rot=(2.0 * math.pi * k / 14.0, 0.0, 0.0),
                  pivot=(0.0, 0.0, 0.0))
    return g


# ---------------------------------------------------------------- 빌드
purge("UGV_")
COL = link_collection("06_Vehicle")

# 출발 지점 — motion-director 가 경로 애니메이션으로 덮어쓴다
_, start_xy = path_tagged("START")
if start_xy is None:
    start_xy = tuple(SPEC["start"]["pos"])
pts = path_xy()
if len(pts) >= 2:
    yaw0 = math.atan2(pts[1][1] - pts[0][1], pts[1][0] - pts[0][0])
else:
    yaw0 = float(SPEC["start"].get("yaw", 0.0))

root = bpy.data.objects.new("UGV_Root", None)
root.empty_display_type = 'PLAIN_AXES'
root.empty_display_size = 0.06
link_to(root, COL)
root.location = (start_xy[0], start_xy[1], 0.0)
root.rotation_euler = (0.0, 0.0, yaw0)
root["length"] = LEN
root["width"] = WID
root["height"] = HGT
root["wheel_r"] = WR
root["wheelbase"] = 2.0 * WHEEL_CX
root["track_width"] = 2.0 * WHEEL_CY
root["forward_axis"] = "+X"

body = geo_build("UGV_Body", body_geo(), BODY_MATS, COL, loc=(0.0, 0.0, 0.0),
                 bevel=0.0008, segments=2)
sensor = geo_build("UGV_Sensor", sensor_geo(), SENSOR_MATS, COL, loc=(0.0, 0.0, 0.0),
                   bevel=0.0006, segments=2)

wheels = []
for tag, sx, sy in (("FL", 1.0, 1.0), ("FR", 1.0, -1.0),
                    ("RL", -1.0, 1.0), ("RR", -1.0, -1.0)):
    w = geo_build("UGV_Wheel_%s" % tag, wheel_geo(), WHEEL_MATS, COL,
                  loc=(sx * WHEEL_CX, sy * WHEEL_CY, WR), bevel=0.0004, segments=2)
    # 메시 축은 로컬 X. 축을 월드 Y 로 세우는 90° 는 delta 에 넣는다 —
    # 그래야 굴림 코드가 rotation_euler 를 통째로 덮어써도 바퀴가 눕지 않는다.
    w.rotation_euler = (0.0, 0.0, 0.0)
    w.delta_rotation_euler = (0.0, 0.0, math.pi * 0.5)
    w["roll_axis"] = "X"
    w["roll_sign"] = 1.0          # +X 전진 시 rotation_euler[0] += dist / wheel_r
    w["wheel_r"] = WR
    w["corner"] = tag
    wheels.append(w)

# 1인칭 카메라 앵커. 참조 사진의 시점 — 노면에서 CAM_Z, CAM_PITCH 만큼 하향.
# 회전 (90+pitch, 0, -90) 이면 카메라 -Z 축이 +X 를 보고 업벡터가 +Z 가 된다.
cam = bpy.data.objects.new("UGV_Cam", None)
cam.empty_display_type = 'ARROWS'
cam.empty_display_size = 0.03
link_to(cam, COL)
cam.location = (HX - 0.004, 0.0, CAM_Z)
cam.rotation_euler = (math.radians(90.0 + CAM_PITCH), 0.0, math.radians(-90.0))
cam["pitch_deg"] = CAM_PITCH
cam["height_m"] = CAM_Z
cam["note"] = "camera -Z looks along parent +X; clip_start <= 0.005"

for ob in [body, sensor, cam] + wheels:
    ob.parent = root          # matrix_parent_inverse 는 단위행렬 그대로 둔다

# ---------------------------------------------------------------- 검산 출력
vz = [v.co.z for v in body.data.vertices] + [v.co.z for v in sensor.data.vertices]
top = max(vz)
outer = WHEEL_CY + WW * 0.5
names = ["UGV_Root", "UGV_Body", "UGV_Wheel_FL", "UGV_Wheel_FR",
         "UGV_Wheel_RL", "UGV_Wheel_RR", "UGV_Sensor", "UGV_Cam"]
missing = [n for n in names if n not in bpy.data.objects]

print("  치수  전장 %.3f / 전폭 %.3f (차선 %.2f 대비 %.0f%%) / 전고 %.3f"
      % (LEN, outer * 2.0, LANE_W, outer * 2.0 / LANE_W * 100.0, top))
print("  바퀴  r=%.3f w=%.3f  휠베이스 %.3f  윤거 %.3f  원점=바퀴 중심(굴림 예외)"
      % (WR, WW, 2.0 * WHEEL_CX, 2.0 * WHEEL_CY))
print("  카메라 UGV_Cam @ (%.3f, 0, %.3f) pitch=%.1f°  전방 +X"
      % (HX - 0.004, CAM_Z, CAM_PITCH))
print("  배치  UGV_Root @ (%.3f, %.3f, 0) yaw=%.3f rad (START 태그, motion-director 가 덮어씀)"
      % (start_xy[0], start_xy[1], yaw0))

print("[70_vehicle] built %d objects in 06_Vehicle | parts=%s | missing=%s"
      % (len(COL.objects), "/".join(n.replace("UGV_", "") for n in names),
         missing if missing else "none"))
