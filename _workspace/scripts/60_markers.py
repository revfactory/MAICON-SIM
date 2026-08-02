# -*- coding: utf-8 -*-
"""
60_markers.py — ArUco 마커 보드 프로토타입 (asset-modeler 산출)

참조 사진의 경기장에는 각 객체 옆에 흰 판 + 검은 마커가 세워져 있다. 1인칭 샷에서
마커가 보이는 것이 이 대회의 시각적 정체성이라 그대로 재현한다.

생성물
    _PROTO_marker        판 + 검은 프레임 + A자 스탠드를 합친 **단일 메시** (숨김 _Proto)
    ARU_TEX_00           프로토타입 기본 패턴 이미지
    ARU_MAT_00           프로토타입 기본 마커 머티리얼
    ARU_TEX_01 ~ _23     23개 객체 포지션별 패턴 이미지
    ARU_MAT_01 ~ _23     23개 포지션별 마커 머티리얼
    _PROTO_qr            QR 아군표식 보드 (과제2). ArUco 보드와 **같은 스탠드 구조**
    QR_TEX_04 / QR_MAT_04  QR 패턴 이미지·머티리얼 (spec.qr_marker.pattern_id 기준)

마커 패턴은 외부 이미지가 아니라 bpy.data.images.new() 로 픽셀 버퍼를 직접 채워
만든다. 외부 파일에 의존하면 재현성이 깨진다.

마커 ID 인코딩 (나중에 인식 파이프라인을 붙일 때 그대로 쓸 수 있다)
    code = (kind_id << 5) | pos_id        # 8비트, kind_id 0~6, pos_id 1~23
    word = (code << 8) | (~code & 0xFF)   # 16비트 = 4x4 비트. 하위 바이트를 보수로
                                          # 채워 흑백 비율을 맞추고 오검출을 줄인다
    복호: kind_id = code >> 5,  pos_id = code & 0x1F

--------------------------------------------------------------------------
scene-dresser 사용법 — 인스턴스마다 다른 마커를 붙이는 법
--------------------------------------------------------------------------
메시를 공유하면 머티리얼도 공유된다. 그래서 프로토타입의 마커 슬롯만
link='OBJECT' 로 만들어 두었다. 복제 후 오브젝트 레벨에서 갈아끼우면 된다:

    inst = proto.copy(); inst.data = proto.data
    inst.material_slots[MARKER_SLOT].link = 'OBJECT'          # 복제 시 유지되지만 명시
    inst.material_slots[MARKER_SLOT].material = bpy.data.materials["ARU_MAT_%02d" % pid]

MARKER_SLOT 인덱스는 프로토타입의 커스텀 프로퍼티 proto["marker_slot"] 에 들어 있다.
판의 법선은 로컬 +X 다. 따라서 marker_dir 방향을 바라보게 하려면
    inst.rotation_euler = (0, 0, math.atan2(dir[1], dir[0]))

QR 아군표식(_PROTO_qr)도 같은 계약을 따른다. 다만 패턴이 1종뿐이라 슬롯 교체가
필요 없고, 배치 좌표/헤딩은 spec.qr_marker 의 pos / yaw 를 그대로 쓰면 된다
(프로토타입 커스텀 프로퍼티 qr["pos"], qr["yaw"] 에도 같은 값을 심어 두었다).
"""

import bpy
import bmesh
import math
import os

WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
exec(open(os.path.join(WORKSPACE, "scripts", "00_common.py")).read())

MK = SPEC.get("markers", {})
BW = float(MK.get("size", 0.05))            # 판 한 변 0.05
FW = float(MK.get("frame_w", 0.006))        # 검은 프레임 폭
PT = 0.004                                  # 판 두께 (X)
STAND_H = 0.014                             # 판 하단 높이 → 전체 높이 = STAND_H + BW
FRONT_FRAME = 0.0008                        # 프레임 돌출
FRONT_MARK = 0.0006                         # 마커 면 돌출 (프레임보다 낮게 = 안쪽)

IMG_CELL = 8                                # 격자 한 칸 픽셀
IMG_N = 8                                   # 6x6 마커 + 사방 1칸 흰 여백
IMG_SIZE = IMG_CELL * IMG_N                 # 64 px
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
    off = len(g["v"])
    for p in sub["v"]:
        g["v"].append(_xf(p, rot, pivot, trans))
    for fc, mi, sm in zip(sub["f"], sub["mi"], sub["sm"]):
        g["f"].append(tuple(i + off for i in fc))
        g["mi"].append(mi)
        g["sm"].append(sm)
    return g


def add_box(g, x0, x1, y0, y1, z0, z1, mi=0):
    """반환값은 이 박스의 +X 면 폴리곤 인덱스 — 마커 면 UV 를 찾는 데 쓴다."""
    plus_x_face = len(g["f"]) + 3
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    geo_add(g, v, f, mi=mi)
    return plus_x_face


def add_boxc(g, cx, cy, z0, w, d, h, mi=0):
    return add_box(g, cx - w * 0.5, cx + w * 0.5,
                   cy - d * 0.5, cy + d * 0.5, z0, z0 + h, mi=mi)


def add_strut(g, p0, p1, w, mi=0):
    dx, dy, dz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    L = math.sqrt(dx * dx + dy * dy + dz * dz)
    if L < 1e-9:
        return g
    th = math.acos(max(-1.0, min(1.0, dz / L)))
    ps = math.atan2(dy, dx)
    sub = geo_new()
    add_boxc(sub, 0.0, 0.0, 0.0, w, w, L, mi=mi)
    return geo_merge(g, sub, rot=(0.0, th, ps), pivot=(0.0, 0.0, 0.0), trans=p0)


def geo_build(name, g, mats, col, loc=(0.0, 0.0, 0.0), bevel=0.0005, segments=2):
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


# ---------------------------------------------------------------- 마커 패턴
def marker_code(kind_id, pos_id):
    return ((int(kind_id) & 0x07) << 5) | (int(pos_id) & 0x1F)


def marker_bits(code):
    """8비트 코드 → 4x4 불리언 (True = 흰색). 위→아래, 왼→오른 순서."""
    code &= 0xFF
    word = (code << 8) | ((~code) & 0xFF)
    bits = []
    for r in range(4):
        row = []
        for c in range(4):
            row.append(bool((word >> (15 - (r * 4 + c))) & 1))
        bits.append(row)
    return bits


def make_marker_image(name, bits):
    """6x6 ArUco(테두리 1칸 검정 + 내부 4x4 비트) + 사방 1칸 흰 여백을 픽셀로 굽는다."""
    img = bpy.data.images.get(name)
    if img is not None and (img.size[0] != IMG_SIZE or img.size[1] != IMG_SIZE):
        bpy.data.images.remove(img)
        img = None
    if img is None:
        img = bpy.data.images.new(name, width=IMG_SIZE, height=IMG_SIZE, alpha=False)

    px = [1.0] * (IMG_SIZE * IMG_SIZE * 4)
    last = IMG_N - 1
    for py in range(IMG_SIZE):
        gy = py // IMG_CELL
        for pxi in range(IMG_SIZE):
            gx = pxi // IMG_CELL
            if gx == 0 or gy == 0 or gx == last or gy == last:
                v = 1.0                                   # 흰 여백(quiet zone)
            else:
                mx, my = gx - 1, gy - 1                   # 마커 내부 0~5
                if mx == 0 or my == 0 or mx == 5 or my == 5:
                    v = 0.0                               # ArUco 검은 테두리
                else:
                    # 이미지 행은 아래에서 위로 쌓이므로 비트 행을 뒤집어 읽는다
                    v = 1.0 if bits[4 - my][mx - 1] else 0.0
            i = (py * IMG_SIZE + pxi) * 4
            px[i] = px[i + 1] = px[i + 2] = v
    img.pixels = px
    try:
        img.colorspace_settings.name = 'sRGB'
    except Exception:
        pass
    try:
        img.pack()          # .blend 저장 시 패턴이 같이 따라가도록
    except Exception:
        pass
    return img


def make_marker_material(name, img):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (420.0, 0.0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (120.0, 0.0)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.location = (-240.0, 0.0)
    tex.image = img
    tex.interpolation = 'Closest'       # 픽셀이 뭉개지면 마커가 아니게 된다
    tex.extension = 'EXTEND'
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    _set_input(bsdf, "Roughness", 0.62)
    _set_input(bsdf, "Metallic", 0.0)
    mat.diffuse_color = (0.75, 0.75, 0.75, 1.0)
    return mat


# ---------------------------------------------------------------- 보드 지오메트리
def board_geo():
    """판 + 프레임 + A자 스탠드를 한 메시로. 마커 면의 폴리곤 인덱스를 함께 반환한다.

    로컬 +X 가 판의 법선(마커가 보이는 쪽), 원점은 스탠드 바닥(z=0).
    """
    g = geo_new()
    z0, z1 = STAND_H, STAND_H + BW
    hy = BW * 0.5

    add_box(g, -PT, 0.0, -hy, hy, z0, z1, mi=0)                       # 흰 판

    fx = FRONT_FRAME
    add_box(g, 0.0, fx, -hy, hy, z0, z0 + FW, mi=1)                   # 프레임 하
    add_box(g, 0.0, fx, -hy, hy, z1 - FW, z1, mi=1)                   # 프레임 상
    add_box(g, 0.0, fx, -hy, -hy + FW, z0 + FW, z1 - FW, mi=1)        # 프레임 좌
    add_box(g, 0.0, fx, hy - FW, hy, z0 + FW, z1 - FW, mi=1)          # 프레임 우

    my0, my1 = -hy + FW, hy - FW
    mz0, mz1 = z0 + FW, z1 - FW
    face_idx = add_box(g, 0.0, FRONT_MARK, my0, my1, mz0, mz1, mi=2)  # 마커 면

    # A자 스탠드
    add_box(g, -PT - 0.002, -PT, -0.007, 0.007, z0 + 0.004, z1 - 0.004, mi=3)  # 등뼈
    for sy in (-1.0, 1.0):
        a, b = sorted((sy * 0.016, sy * 0.022))
        add_box(g, -PT, 0.0, a, b, 0.0, z0, mi=3)                     # 앞 다리
        c, e = sorted((sy * 0.014, sy * 0.024))
        add_box(g, -0.011, 0.004, c, e, 0.0, 0.003, mi=3)             # 앞 발
    add_box(g, -PT, -0.001, -0.020, 0.020, 0.005, 0.008, mi=3)        # 가로대
    add_strut(g, (-0.003, 0.0, z0 + 0.030), (-0.030, 0.0, 0.003), 0.005, mi=3)
    add_boxc(g, -0.030, 0.0, 0.0, 0.013, 0.016, 0.004, mi=3)          # 뒤 발
    return g, face_idx, (my0, my1, mz0, mz1)


def set_marker_uv(ob, face_idx, box):
    """마커 면에만 UV 를 깐다. 와인딩과 무관하게 정점 좌표에서 직접 계산한다.

    +X 에서 바라보는 관측자의 오른쪽은 -Y 다. 그래서 u 는 y 가 줄어드는 방향으로
    증가시킨다 — 안 그러면 마커가 좌우 반전돼 실제 디코딩이 불가능해진다.
    """
    me = ob.data
    my0, my1, mz0, mz1 = box
    uv = me.uv_layers.get("UVMap")
    if uv is None:
        uv = me.uv_layers.new(name="UVMap")
    if face_idx >= len(me.polygons):
        return False
    poly = me.polygons[face_idx]
    for li in poly.loop_indices:
        co = me.vertices[me.loops[li].vertex_index].co
        u = (my1 - co.y) / max(1e-9, my1 - my0)
        v = (co.z - mz0) / max(1e-9, mz1 - mz0)
        uv.data[li].uv = (u, v)
    return True


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
    _lc.hide_viewport = True


# ---------------------------------------------------------------- 머티리얼
M_PLATE = get_or_create_material("ARU_Plate", color=[0.88, 0.88, 0.86], roughness=0.60)
M_FRAME = get_or_create_material("ARU_Frame", color=[0.030, 0.030, 0.035], roughness=0.66)
M_STAND = get_or_create_material("ARU_Stand", color=[0.26, 0.27, 0.29],
                                 roughness=0.45, metallic=0.55)


# ---------------------------------------------------------------- 패턴 굽기
KIND_ID = {k: int(v["id"]) for k, v in SPEC["object_kinds"].items()}

pattern = []                                        # (mat_name, code, kind, pos_id)
img0 = make_marker_image("ARU_TEX_00", marker_bits(marker_code(0, 0)))
mat0 = make_marker_material("ARU_MAT_00", img0)
mat0["marker_code"] = marker_code(0, 0)
mat0["kind"] = "proto"
mat0["pos_id"] = 0

for o in SPEC["objects"]:
    pid = int(o["id"])
    kind = o["kind"]
    code = marker_code(KIND_ID.get(kind, 7), pid)
    img = make_marker_image("ARU_TEX_%02d" % pid, marker_bits(code))
    mat = make_marker_material("ARU_MAT_%02d" % pid, img)
    mat["marker_code"] = code
    mat["kind"] = kind
    mat["pos_id"] = pid
    pattern.append(("ARU_MAT_%02d" % pid, code, kind, pid))


# ---------------------------------------------------------------- 보드 프로토타입
purge("_PROTO_marker")

G, FACE_IDX, MBOX = board_geo()
BOARD = geo_build("_PROTO_marker", G, [M_PLATE, M_FRAME, mat0, M_STAND],
                  PROTO, loc=(0.0, 0.0, 0.0), bevel=0.0005, segments=2)
uv_ok = set_marker_uv(BOARD, FACE_IDX, MBOX)

MARKER_SLOT = 2
if len(BOARD.material_slots) > MARKER_SLOT:
    # 인스턴스마다 다른 마커를 붙일 수 있도록 이 슬롯만 오브젝트 레벨로 뺀다.
    BOARD.material_slots[MARKER_SLOT].link = 'OBJECT'
    BOARD.material_slots[MARKER_SLOT].material = mat0

BOARD["marker_slot"] = MARKER_SLOT
BOARD["face_normal_axis"] = "+X"
BOARD["plate_size"] = BW
BOARD["total_h"] = STAND_H + BW
BOARD["marker_mat_fmt"] = "ARU_MAT_%02d"

print("  _PROTO_marker  plate=%.3fm  total_h=%.3fm  verts=%d faces=%d  uv=%s  slot=%d(+X 법선)"
      % (BW, STAND_H + BW, len(BOARD.data.vertices), len(BOARD.data.polygons),
         "ok" if uv_ok else "FAIL", MARKER_SLOT))
for name, code, kind, pid in pattern[:4]:
    print("  %s  code=0x%02X (kind=%s id=%d, pos=%d)" % (name, code, kind,
                                                         KIND_ID.get(kind, -1), pid))
print("  ... 총 %d 종 (ARU_MAT_01 ~ ARU_MAT_%02d)" % (len(pattern), len(pattern)))


# =========================================================================
# QR 아군표식 (과제2) — spec.qr_marker
#
# 위의 ArUco 로직은 한 줄도 고치지 않았다. 보드 지오메트리(board_geo)와 UV
# 매핑(set_marker_uv)만 재사용해 판 위 패턴을 QR 로 바꾼 프로토타입 1개를 얹는다.
#
# ArUco 와 QR 을 눈으로 가르는 것은 결국 **3개 모서리의 파인더 패턴**이다
# (좌상·우상·좌하의 겹친 사각형 7x7). 그래서 이 세 개를 먼저 정확히 박고,
# 타이밍 패턴·다크 모듈까지 규격대로 넣은 뒤, 남은 데이터 영역만
# pattern_id 에서 결정적으로 채운다. 실제 디코딩은 되지 않지만 — 데모 영상에서
# 요구되는 것은 "QR 로 보이는가" 이고 그건 파인더 패턴이 결정한다.
# =========================================================================
QRC = SPEC.get("qr_marker", {})
QR_ID = int(QRC.get("pattern_id", 0))
QR_COUNT = int(QRC.get("pattern_count", 9))
QR_SIZE = float(QRC.get("size", BW))

QR_MOD = 21          # QR version 1 (21x21 모듈)
QR_QUIET = 4         # 규격 여백 4모듈 — 이게 없으면 스캐너가 못 읽고, 눈으로도 답답하다
QR_CELL = 6          # 모듈당 픽셀
QR_N = QR_MOD + QR_QUIET * 2
QR_PX = QR_N * QR_CELL


def qr_data_bit(pid, r, c):
    """pattern_id 와 (행,열)에서 결정적으로 만드는 데이터 비트. 흑백이 대략 반반이다."""
    v = ((int(pid) & 0xFF) + 1) * 0x9E3779B1
    v = (v ^ ((r + 1) * 0x85EBCA6B)) & 0xFFFFFFFF
    v = (v * 0xC2B2AE35) & 0xFFFFFFFF
    v = (v ^ ((c + 1) * 0x27D4EB2F)) & 0xFFFFFFFF
    v = (v ^ (v >> 15)) & 0xFFFFFFFF
    v = (v * 0x2545F491) & 0xFFFFFFFF
    v ^= (v >> 13)
    return bool(v & 1)


def qr_modules(pid, n=QR_MOD):
    """True = 검은 모듈. r=0 이 위쪽 행, c=0 이 왼쪽 열 (QR 표준 방향)."""
    m = [[False] * n for _ in range(n)]
    fixed = [[False] * n for _ in range(n)]

    # 파인더 패턴 3개 + 분리자(흰 1모듈 띠). QR 의 정체성이 여기에 있다.
    for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = r0 + dr, c0 + dc
                if not (0 <= r < n and 0 <= c < n):
                    continue
                fixed[r][c] = True
                if 0 <= dr < 7 and 0 <= dc < 7:
                    ring = max(abs(dr - 3), abs(dc - 3))
                    m[r][c] = ring in (0, 1, 3)   # 3x3 검정 / 흰 링 / 7x7 검은 테두리
                else:
                    m[r][c] = False               # 분리자

    # 타이밍 패턴 (행 6 / 열 6 의 흑백 교대) — 파인더 사이를 잇는 눈금
    for i in range(8, n - 8):
        m[6][i] = (i % 2 == 0)
        fixed[6][i] = True
        m[i][6] = (i % 2 == 0)
        fixed[i][6] = True

    # 다크 모듈 (4*version+9, 8) — version 1 이면 (13, 8). 항상 검정이다
    m[n - 8][8] = True
    fixed[n - 8][8] = True

    for r in range(n):
        for c in range(n):
            if not fixed[r][c]:
                m[r][c] = qr_data_bit(pid, r, c)
    return m


def make_qr_image(name, mods):
    """QR 모듈 격자를 픽셀 버퍼로 굽는다 (외부 이미지 금지 — 재현성)."""
    img = bpy.data.images.get(name)
    if img is not None and (img.size[0] != QR_PX or img.size[1] != QR_PX):
        bpy.data.images.remove(img)
        img = None
    if img is None:
        img = bpy.data.images.new(name, width=QR_PX, height=QR_PX, alpha=False)

    px = [1.0] * (QR_PX * QR_PX * 4)
    for py in range(QR_PX):
        # 이미지 행은 아래에서 위로 쌓인다. QR 행은 위에서 아래이므로 뒤집어 읽는다
        mr = QR_MOD - 1 - (py // QR_CELL - QR_QUIET)
        row_ok = 0 <= mr < QR_MOD
        for pxi in range(QR_PX):
            mc = pxi // QR_CELL - QR_QUIET
            v = 0.0 if (row_ok and 0 <= mc < QR_MOD and mods[mr][mc]) else 1.0
            i = (py * QR_PX + pxi) * 4
            px[i] = px[i + 1] = px[i + 2] = v
    img.pixels = px
    try:
        img.colorspace_settings.name = 'sRGB'
    except Exception:
        pass
    try:
        img.pack()
    except Exception:
        pass
    return img


purge("_PROTO_qr")

# 아군표식 프레임은 짙은 남색이다. ArUco(검정)와 한눈에 갈리게 하려는 의도적 선택 —
# 영상에서 "적 객체 마커 24개 사이의 아군표식 1개"가 색으로 즉시 구분된다.
M_QR_FRAME = get_or_create_material("QR_Frame", color=[0.05, 0.09, 0.20], roughness=0.55)

QR_MODS = qr_modules(QR_ID)
qr_img = make_qr_image("QR_TEX_%02d" % QR_ID, QR_MODS)
qr_mat = make_marker_material("QR_MAT_%02d" % QR_ID, qr_img)
qr_mat["pattern_id"] = QR_ID
qr_mat["pattern_count"] = QR_COUNT
qr_mat["kind"] = "qr_friendly"

G_QR, FACE_QR, MBOX_QR = board_geo()
QR_BOARD = geo_build("_PROTO_qr", G_QR, [M_PLATE, M_QR_FRAME, qr_mat, M_STAND],
                     PROTO, loc=(0.0, 0.0, 0.0), bevel=0.0005, segments=2)
qr_uv_ok = set_marker_uv(QR_BOARD, FACE_QR, MBOX_QR)

if len(QR_BOARD.material_slots) > MARKER_SLOT:
    QR_BOARD.material_slots[MARKER_SLOT].link = 'OBJECT'
    QR_BOARD.material_slots[MARKER_SLOT].material = qr_mat

QR_BOARD["marker_slot"] = MARKER_SLOT
QR_BOARD["marker_mat_fmt"] = "QR_MAT_%02d"
QR_BOARD["face_normal_axis"] = "+X"
QR_BOARD["plate_size"] = BW
QR_BOARD["total_h"] = STAND_H + BW
QR_BOARD["pattern_id"] = QR_ID
QR_BOARD["pattern_count"] = QR_COUNT
QR_BOARD["modules"] = QR_MOD
QR_BOARD["pos"] = [float(v) for v in QRC.get("pos", [0.0, 0.0])]
QR_BOARD["yaw"] = float(QRC.get("yaw", 0.0))
QR_BOARD["note"] = "friendly-force QR (task 2). place at spec.qr_marker pos/yaw"

_dark = sum(1 for row in QR_MODS for v in row if v)
if abs(QR_SIZE - BW) > 1e-6:
    print("  [!] spec.qr_marker.size %.3f 와 markers.size %.3f 가 다르다 — 판은 markers.size 를 따랐다"
          % (QR_SIZE, BW))
print("  _PROTO_qr      plate=%.3fm  total_h=%.3fm  verts=%d faces=%d  uv=%s  slot=%d(+X 법선)"
      % (BW, STAND_H + BW, len(QR_BOARD.data.vertices), len(QR_BOARD.data.polygons),
         "ok" if qr_uv_ok else "FAIL", MARKER_SLOT))
print("  QR_MAT_%02d      %dx%d px | %d 모듈 + 여백 %d | 파인더 3개(좌상·우상·좌하) + 타이밍 + 다크모듈 | "
      "검은 모듈 %d/%d (%.0f%%) | pattern %d/%d"
      % (QR_ID, QR_PX, QR_PX, QR_MOD, QR_QUIET, _dark, QR_MOD * QR_MOD,
         _dark * 100.0 / (QR_MOD * QR_MOD), QR_ID, QR_COUNT))
print("  QR 배치 좌표(scene-dresser용) pos=(%.2f, %.2f) yaw=%.4f rad"
      % (QR_BOARD["pos"][0], QR_BOARD["pos"][1], QR_BOARD["yaw"]))

print("[60_markers] built 2 prototypes (_PROTO_marker / _PROTO_qr) + %d ArUco textures/materials "
      "(%dx%d px, 6x6) + 1 QR texture/material (%dx%d px, 21x21) "
      "| scene-dresser 는 inst.material_slots[%d].material 로 교체한다"
      % (len(pattern) + 1, IMG_SIZE, IMG_SIZE, QR_PX, QR_PX, MARKER_SLOT))
