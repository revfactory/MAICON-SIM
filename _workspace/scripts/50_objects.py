# -*- coding: utf-8 -*-
"""
50_objects.py — 객체 7종 프로토타입 (asset-modeler 산출)

spec/track_spec.json 의 object_kinds 7종을 각각 1개씩만 만들어 숨김 컬렉션
`_Proto` 에 넣는다. 배치는 55_placement.py 가 메시를 공유하는 복제로 처리한다.

    proto = bpy.data.objects["_PROTO_tank"]
    inst = proto.copy()
    inst.data = proto.data        # 메시 공유 — 23개가 메모리를 거의 안 쓴다
    inst.name = "OBJ_11_tank"

프로토타입은 **반드시 단일 메시**다. 전차의 차체·포탑·포신도 정점을 한 메시에
합쳐 넣는다. 여러 오브젝트로 두면 복제가 부모-자식 관계까지 복사해야 하고
검수의 개수 카운트가 깨진다.

형태보다 실루엣: 데모 영상에서 객체는 수십 픽셀이다. 표면 디테일 대신 멀리서도
종류가 갈리는 윤곽에 투자한다. 색도 채도를 벌려 놓았다 — 전부 올리브면 영상에서
분간되지 않는다.

    missile  올리브 + 붉은 노즈 (누운 원통 + 원뿔 + X자 핀)
    hazmat   노랑 드럼 + 검정 밴드   ← 유일하게 고채도, 즉시 구분된다
    mortar   짙은 올리브, 경사 포신 + 이각대
    tank     카키, 납작 차체 + 포탑 + 긴 포신
    enemy    적갈색 세로 인형        ← 유일하게 세로로 긴 실루엣
    ammo_box 올리브 그린 보강 상자
    vehicle  회청색 픽업 (캐빈 + 유리 + 바퀴 4)
"""

import bpy
import bmesh
import math
import os

WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
exec(open(os.path.join(WORKSPACE, "scripts", "00_common.py")).read())

BEVEL_OBJ = 0.0005      # 0.5 mm — 3~16 cm 객체에서 직각을 죽이는 최소치
PROTO_COL_NAME = "_Proto"


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
    """sub 버퍼를 회전·이동해 g 에 합친다 (경사 포신, 이각대 다리 등)."""
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


def add_cone(g, base, r, length, axis='Z', seg=16, mi=0, smooth=True):
    bx, by, bz = base
    v = []
    for i in range(seg):
        a = 2.0 * math.pi * i / seg
        cc, ss = math.cos(a), math.sin(a)
        if axis == 'X':
            v.append((bx, by + r * cc, bz + r * ss))
        elif axis == 'Y':
            v.append((bx + r * ss, by, bz + r * cc))
        else:
            v.append((bx + r * cc, by + r * ss, bz))
    if axis == 'X':
        v.append((bx + length, by, bz))
    elif axis == 'Y':
        v.append((bx, by + length, bz))
    else:
        v.append((bx, by, bz + length))
    f = [(i, (i + 1) % seg, seg) for i in range(seg)]
    sm = [smooth] * seg
    f.append(tuple(range(seg - 1, -1, -1)))
    sm.append(False)
    return geo_add(g, v, f, mi=mi, smooth=sm)


def add_prism_xz(g, profile, y0, y1, mi=0):
    """XZ 단면(볼록 다각형)을 Y 방향으로 압출. 차체 경사면을 싸게 만든다."""
    n = len(profile)
    v = [(p[0], y0, p[1]) for p in profile] + [(p[0], y1, p[1]) for p in profile]
    f = []
    for i in range(n):
        j = (i + 1) % n
        f.append((i, j, n + j, n + i))
    f.append(tuple(range(n - 1, -1, -1)))
    f.append(tuple(range(n, 2 * n)))
    return geo_add(g, v, f, mi=mi)


def add_strut(g, p0, p1, w, mi=0, seg=None):
    """두 점을 잇는 각재/봉 (이각대, 스탠드 다리)."""
    dx, dy, dz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    L = math.sqrt(dx * dx + dy * dy + dz * dz)
    if L < 1e-9:
        return g
    th = math.acos(max(-1.0, min(1.0, dz / L)))
    ps = math.atan2(dy, dx)
    sub = geo_new()
    if seg:
        add_cyl(sub, (0.0, 0.0, 0.0), w * 0.5, L, axis='Z', seg=seg, mi=mi, smooth=True)
    else:
        add_boxc(sub, 0.0, 0.0, 0.0, w, w, L, mi=mi)
    return geo_merge(g, sub, rot=(0.0, th, ps), pivot=(0.0, 0.0, 0.0), trans=p0)


def geo_build(name, g, mats, col, loc=(0.0, 0.0, 0.0), bevel=BEVEL_OBJ, segments=2):
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


def geo_bbox(g):
    xs = [p[0] for p in g["v"]]
    ys = [p[1] for p in g["v"]]
    zs = [p[2] for p in g["v"]]
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


# ---------------------------------------------------------------- 머티리얼
M_OLIVE = get_or_create_material("OBJ_Olive", color=[0.30, 0.32, 0.18], roughness=0.76)
M_RED = get_or_create_material("OBJ_Red", color=[0.62, 0.11, 0.09], roughness=0.52)
M_STEEL = get_or_create_material("OBJ_Steel", color=[0.32, 0.33, 0.35], roughness=0.42, metallic=0.70)
M_DARK = get_or_create_material("OBJ_Dark", color=[0.055, 0.055, 0.065], roughness=0.72)
M_YELLOW = get_or_create_material("OBJ_Yellow", color=[0.90, 0.75, 0.08], roughness=0.44)
M_KHAKI = get_or_create_material("OBJ_Khaki", color=[0.42, 0.40, 0.26], roughness=0.76)
M_DOLIVE = get_or_create_material("OBJ_DarkOlive", color=[0.18, 0.20, 0.14], roughness=0.78)
M_RUST = get_or_create_material("OBJ_Rust", color=[0.35, 0.16, 0.13], roughness=0.82)
M_RUSTD = get_or_create_material("OBJ_RustDark", color=[0.20, 0.09, 0.08], roughness=0.80)
M_GREEN = get_or_create_material("OBJ_Green", color=[0.28, 0.34, 0.20], roughness=0.72)
M_GREENL = get_or_create_material("OBJ_GreenLight", color=[0.38, 0.45, 0.27], roughness=0.68)
M_SLATE = get_or_create_material("OBJ_Slate", color=[0.36, 0.42, 0.48], roughness=0.34)
M_GLASS = get_or_create_material("OBJ_Glass", color=[0.035, 0.045, 0.060], roughness=0.10, metallic=0.25)
M_LAMP = get_or_create_material("OBJ_Lamp", color=[0.95, 0.90, 0.72], roughness=0.20,
                                emission=[1.0, 0.90, 0.62], emission_strength=3.0)


# ---------------------------------------------------------------- 숨김 컬렉션
def _find_layer_col(lc, name):
    if lc.collection.name == name:
        return lc
    for ch in lc.children:
        r = _find_layer_col(ch, name)
        if r is not None:
            return r
    return None


PROTO = link_collection(PROTO_COL_NAME)
PROTO.hide_render = True
PROTO.hide_viewport = True
_lc = _find_layer_col(bpy.context.view_layer.layer_collection, PROTO_COL_NAME)
if _lc is not None:
    _lc.hide_viewport = True        # 아웃라이너 눈 아이콘 — exclude 는 쓰지 않는다
                                    # (exclude 하면 복제 시 평가가 꼬일 수 있다)


def make_proto(kind, g, mats):
    name = "_PROTO_%s" % kind
    ob = geo_build(name, g, mats, PROTO, loc=(0.0, 0.0, 0.0))
    info = SPEC["object_kinds"].get(kind, {})
    ob["kind"] = kind
    ob["kind_id"] = int(info.get("id", -1))
    bb = geo_bbox(g)
    ob["bbox"] = [round(v, 4) for v in bb]
    return ob, bb


# 각 종류만 정확히 지운다. purge("_PROTO_") 로 싹 지우면 60_markers 가 만든
# _PROTO_marker 까지 날아가 재실행 순서에 따라 배치가 조용히 깨진다.
KINDS = ["missile", "hazmat", "mortar", "tank", "enemy", "ammo_box", "vehicle"]
for _k in KINDS:
    purge("_PROTO_%s" % _k)


# ================================================================ 1. missile
# 0.16 x 0.03 x 0.03 — 낮은 발사 거치대 위에 3° 들린 원통 + 붉은 원뿔 노즈.
# 노즈를 붉게 칠하면 멀리서도 "뾰족한 빨간 끝"으로 즉시 읽힌다.
def geo_missile():
    g = geo_new()
    AX = 0.0155                                   # 탄체 중심선 높이
    add_box(g, -0.070, 0.062, -0.014, 0.014, 0.0, 0.003, mi=3)      # 거치대 판
    add_boxc(g, -0.050, 0.0, 0.003, 0.013, 0.026, 0.003, mi=2)      # 후방 새들
    add_boxc(g, 0.030, 0.0, 0.003, 0.013, 0.026, 0.003, mi=2)       # 전방 새들
    add_boxc(g, -0.050, 0.0, 0.0, 0.020, 0.030, 0.003, mi=2)        # 받침 보강
    add_boxc(g, 0.030, 0.0, 0.0, 0.020, 0.030, 0.003, mi=2)

    m = geo_new()
    add_cyl(m, (-0.068, 0.0, AX), 0.0095, 0.108, axis='X', seg=18, mi=0, smooth=True)
    add_cyl(m, (-0.014, 0.0, AX), 0.0102, 0.012, axis='X', seg=18, mi=1, smooth=True)
    add_cyl(m, (0.016, 0.0, AX), 0.0102, 0.008, axis='X', seg=18, mi=1, smooth=True)
    add_cone(m, (0.040, 0.0, AX), 0.0095, 0.032, axis='X', seg=18, mi=1, smooth=True)
    add_cyl(m, (-0.075, 0.0, AX), 0.0068, 0.008, axis='X', seg=16, mi=3, smooth=True)
    for k in range(4):                                              # X자 후미 핀
        fin = geo_new()
        add_box(fin, -0.066, -0.040, -0.0010, 0.0010, AX + 0.004, AX + 0.017, mi=0)
        geo_merge(m, fin, rot=(math.pi * 0.25 + k * math.pi * 0.5, 0.0, 0.0),
                  pivot=(0.0, 0.0, AX))
    geo_merge(g, m, rot=(0.0, -math.radians(3.0), 0.0), pivot=(-0.050, 0.0, AX))
    return g


# ================================================================ 2. hazmat
# 0.05 x 0.05 x 0.07 — 드럼통. 고채도 노랑 + 검정 밴드로 7종 중 가장 눈에 띈다.
def geo_hazmat():
    g = geo_new()
    add_cyl(g, (0.0, 0.0, 0.003), 0.0235, 0.062, seg=22, mi=0, smooth=True)
    add_cyl(g, (0.0, 0.0, 0.0), 0.0245, 0.006, seg=22, mi=2, smooth=True)      # 하단 링
    add_cyl(g, (0.0, 0.0, 0.059), 0.0245, 0.006, seg=22, mi=2, smooth=True)    # 상단 링
    add_cyl(g, (0.0, 0.0, 0.018), 0.0246, 0.005, seg=22, mi=1, smooth=True)    # 위험 밴드
    add_cyl(g, (0.0, 0.0, 0.045), 0.0246, 0.005, seg=22, mi=1, smooth=True)
    add_cyl(g, (0.0, 0.0, 0.065), 0.0210, 0.004, seg=22, mi=0, smooth=True)    # 뚜껑
    add_cyl(g, (0.009, 0.0, 0.069), 0.0042, 0.002, seg=12, mi=2, smooth=True)  # 주입구
    add_box(g, 0.0230, 0.0252, -0.0095, 0.0095, 0.0265, 0.0425, mi=1)          # 표식판
    return g


# ================================================================ 3. mortar
# 0.07 x 0.07 x 0.09 — 경사 포신 + 이각대 + 원형 받침판.
def geo_mortar():
    g = geo_new()
    TILT = math.radians(22.0)
    add_cyl(g, (0.0, 0.0, 0.0), 0.028, 0.004, seg=12, mi=0, smooth=False)   # 받침판
    add_boxc(g, 0.0, 0.0, 0.004, 0.046, 0.008, 0.003, mi=0)                 # 보강 리브
    add_boxc(g, 0.0, 0.0, 0.004, 0.008, 0.046, 0.003, mi=0)
    add_cyl(g, (0.010, 0.0, 0.004), 0.0105, 0.007, seg=14, mi=2, smooth=True)  # 소켓

    b = geo_new()
    add_cyl(b, (0.0, 0.0, -0.004), 0.0092, 0.008, seg=16, mi=2, smooth=True)   # 폐쇄기
    add_cyl(b, (0.0, 0.0, 0.0), 0.0075, 0.074, seg=16, mi=1, smooth=True)      # 포신
    add_cyl(b, (0.0, 0.0, 0.070), 0.0092, 0.007, seg=16, mi=2, smooth=True)    # 포구
    geo_merge(g, b, rot=(0.0, -TILT, 0.0), pivot=(0.0, 0.0, 0.0),
              trans=(0.010, 0.0, 0.010))

    # 이각대 — 포신 60% 지점에서 지면으로
    px = 0.010 - 0.048 * math.sin(TILT)
    pz = 0.010 + 0.048 * math.cos(TILT)
    for sy in (-1.0, 1.0):
        add_strut(g, (px, 0.0, pz), (0.030, sy * 0.028, 0.002), 0.0035, mi=0)
        add_boxc(g, 0.030, sy * 0.028, 0.0, 0.014, 0.008, 0.004, mi=0)
    add_strut(g, (0.030, -0.026, 0.010), (0.030, 0.026, 0.010), 0.0028, mi=2)  # 가로대
    return g


# ================================================================ 4. tank
# 0.14 x 0.07 x 0.06 — 납작 차체 + 포탑 + 긴 포신. 실루엣이 가장 가로로 길다.
def geo_tank():
    g = geo_new()
    trk = [(-0.057, 0.004), (-0.050, 0.0), (0.050, 0.0),
           (0.057, 0.004), (0.057, 0.015), (-0.057, 0.015)]
    for sy in (-1.0, 1.0):
        add_prism_xz(g, trk, sy * 0.026 - 0.008, sy * 0.026 + 0.008, mi=1)
        for wx in (-0.034, 0.0, 0.034):
            add_cyl(g, (wx, sy * 0.026 - 0.009, 0.0075), 0.0058, 0.018,
                    axis='Y', seg=12, mi=2, smooth=True)
    hull = [(-0.052, 0.013), (0.058, 0.013), (0.058, 0.021),
            (0.036, 0.032), (-0.052, 0.032)]
    add_prism_xz(g, hull, -0.030, 0.030, mi=0)
    for sy in (-1.0, 1.0):                                   # 측면 적재함
        add_boxc(g, -0.030, sy * 0.032, 0.022, 0.032, 0.006, 0.008, mi=3)
    tur = [(-0.028, 0.032), (0.024, 0.032), (0.026, 0.038),
           (0.022, 0.048), (-0.024, 0.048)]
    add_prism_xz(g, tur, -0.021, 0.021, mi=0)
    add_boxc(g, 0.026, 0.0, 0.034, 0.009, 0.024, 0.011, mi=0)          # 방순
    add_cyl(g, (0.028, 0.0, 0.0405), 0.0035, 0.050, axis='X', seg=16, mi=2, smooth=True)
    add_cyl(g, (0.078, 0.0, 0.0405), 0.0050, 0.008, axis='X', seg=16, mi=1, smooth=True)
    add_cyl(g, (-0.012, 0.008, 0.048), 0.0080, 0.007, seg=14, mi=0, smooth=True)  # 큐폴라
    add_boxc(g, -0.012, 0.008, 0.055, 0.007, 0.016, 0.004, mi=2)                  # 기관총
    add_cyl(g, (-0.020, -0.014, 0.046), 0.0010, 0.016, seg=8, mi=1, smooth=True)  # 안테나
    return g


# ================================================================ 5. enemy
# 0.04 x 0.04 x 0.10 — 세로로 긴 인형. 7종 중 유일하게 높이가 폭의 2.5배다.
def geo_enemy():
    g = geo_new()
    for sy in (-1.0, 1.0):
        add_boxc(g, 0.001, sy * 0.008, 0.006, 0.010, 0.010, 0.036, mi=0)   # 다리
        add_boxc(g, 0.002, sy * 0.008, 0.0, 0.016, 0.011, 0.006, mi=1)     # 군화
        add_boxc(g, 0.0, sy * 0.017, 0.050, 0.010, 0.008, 0.026, mi=0)     # 팔
    add_boxc(g, 0.0, 0.0, 0.042, 0.014, 0.024, 0.010, mi=0)                # 골반
    add_boxc(g, 0.0, 0.0, 0.052, 0.016, 0.026, 0.024, mi=0)                # 몸통
    add_boxc(g, 0.001, 0.0, 0.056, 0.019, 0.028, 0.015, mi=1)              # 방탄조끼
    add_boxc(g, 0.0, 0.0, 0.076, 0.008, 0.008, 0.004, mi=0)                # 목
    add_boxc(g, 0.0, 0.0, 0.080, 0.013, 0.013, 0.010, mi=0)                # 머리
    add_cyl(g, (0.0, 0.0, 0.086), 0.0086, 0.008, seg=14, mi=1, smooth=True)   # 헬멧
    add_cyl(g, (0.0, 0.0, 0.094), 0.0060, 0.004, seg=14, mi=1, smooth=True)
    add_boxc(g, 0.009, -0.007, 0.0605, 0.028, 0.005, 0.005, mi=2)          # 소총
    add_boxc(g, 0.004, -0.007, 0.0545, 0.005, 0.004, 0.007, mi=2)          # 탄창
    return g


# ================================================================ 6. ammo_box
# 0.08 x 0.05 x 0.04 — 모서리 보강 + 손잡이. 낮고 각진 실루엣.
def geo_ammo_box():
    g = geo_new()
    add_box(g, -0.037, 0.037, -0.022, 0.022, 0.0, 0.026, mi=0)
    add_box(g, -0.039, 0.039, -0.024, 0.024, 0.0, 0.004, mi=2)             # 하단 레일
    for sx in (-1.0, 1.0):                                                 # 모서리 보강
        for sy in (-1.0, 1.0):
            x0, x1 = sorted((sx * 0.039, sx * 0.031))
            y0, y1 = sorted((sy * 0.024, sy * 0.016))
            add_box(g, x0, x1, y0, y1, 0.0, 0.026, mi=2)
    add_box(g, -0.040, 0.040, -0.025, 0.025, 0.026, 0.031, mi=1)           # 뚜껑
    add_box(g, -0.034, 0.034, -0.020, 0.020, 0.031, 0.034, mi=1)
    for sx in (-1.0, 1.0):
        add_boxc(g, sx * 0.010, 0.0, 0.034, 0.004, 0.004, 0.003, mi=3)     # 손잡이 기둥
        add_boxc(g, sx * 0.020, -0.0255, 0.020, 0.010, 0.004, 0.010, mi=3) # 걸쇠
    add_boxc(g, 0.0, 0.0, 0.037, 0.028, 0.005, 0.003, mi=3)                # 손잡이 바
    add_box(g, -0.030, 0.030, -0.0256, -0.0244, 0.008, 0.014, mi=1)        # 스텐실 띠
    return g


# ================================================================ 7. vehicle
# 0.12 x 0.06 x 0.05 — 픽업. 유리와 램프가 있어 전차와 헷갈리지 않는다.
def geo_vehicle():
    g = geo_new()
    add_boxc(g, 0.0, 0.0, 0.012, 0.104, 0.046, 0.016, mi=0)                 # 섀시
    add_box(g, 0.012, 0.052, -0.023, 0.023, 0.028, 0.034, mi=0)             # 보닛
    add_box(g, 0.050, 0.058, -0.026, 0.026, 0.014, 0.024, mi=1)             # 앞 범퍼
    add_box(g, -0.058, -0.050, -0.026, 0.026, 0.014, 0.024, mi=1)           # 뒤 범퍼
    add_prism_xz(g, [(-0.018, 0.028), (0.014, 0.028), (0.0128, 0.034),
                     (-0.018, 0.034)], -0.022, 0.022, mi=0)                 # 캐빈 하부
    add_prism_xz(g, [(-0.018, 0.034), (0.0128, 0.034), (0.010, 0.047),
                     (-0.018, 0.047)], -0.0225, 0.0225, mi=2)               # 유리
    add_box(g, -0.020, 0.012, -0.023, 0.023, 0.046, 0.050, mi=0)            # 루프
    add_box(g, -0.052, -0.020, -0.023, 0.023, 0.028, 0.031, mi=0)           # 적재함 바닥
    add_box(g, -0.052, -0.048, -0.023, 0.023, 0.031, 0.042, mi=0)           # 뒷벽
    for sy in (-1.0, 1.0):
        y0, y1 = sorted((sy * 0.023, sy * 0.019))
        add_box(g, -0.052, -0.020, y0, y1, 0.031, 0.042, mi=0)              # 적재함 옆벽
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            wx = sx * 0.033
            by = 0.0225 if sy > 0 else -0.0305          # 타이어 안쪽 면
            hy = 0.0295 if sy > 0 else -0.0311          # 허브캡은 바깥으로 돌출
            add_cyl(g, (wx, by, 0.011), 0.011, 0.008, axis='Y', seg=14,
                    mi=1, smooth=True)
            add_cyl(g, (wx, hy, 0.011), 0.0048, 0.0016, axis='Y',
                    seg=12, mi=4, smooth=True)
        add_boxc(g, 0.0575, sx * 0.016, 0.018, 0.005, 0.009, 0.006, mi=3)   # 전조등
        add_boxc(g, -0.0575, sx * 0.016, 0.018, 0.005, 0.009, 0.006, mi=5)  # 후미등
    return g


# ---------------------------------------------------------------- 빌드
BUILD = [
    ("missile", geo_missile, [M_OLIVE, M_RED, M_STEEL, M_DARK]),
    ("hazmat", geo_hazmat, [M_YELLOW, M_DARK, M_STEEL]),
    ("mortar", geo_mortar, [M_DOLIVE, M_DARK, M_STEEL]),
    ("tank", geo_tank, [M_KHAKI, M_DARK, M_STEEL, M_DOLIVE]),
    ("enemy", geo_enemy, [M_RUST, M_RUSTD, M_DARK]),
    ("ammo_box", geo_ammo_box, [M_GREEN, M_GREENL, M_DARK, M_STEEL]),
    ("vehicle", geo_vehicle, [M_SLATE, M_DARK, M_GLASS, M_LAMP, M_STEEL, M_RED]),
]

made = 0
for kind, fn, mats in BUILD:
    ob, bb = make_proto(kind, fn(), mats)
    spec_sz = SPEC["object_kinds"][kind]["size"]
    made += 1
    print("  _PROTO_%-9s bbox=(%.3f, %.3f, %.3f)  spec=(%.2f, %.2f, %.2f)  "
          "verts=%d faces=%d"
          % (kind, bb[0], bb[1], bb[2], spec_sz[0], spec_sz[1], spec_sz[2],
             len(ob.data.vertices), len(ob.data.polygons)))

missing = [k for k in SPEC["object_kinds"] if ("_PROTO_%s" % k) not in bpy.data.objects]
print("[50_objects] built %d prototypes in hidden collection '%s' | kinds=%d missing=%s"
      % (made, PROTO_COL_NAME, len(SPEC["object_kinds"]), missing if missing else "none"))
