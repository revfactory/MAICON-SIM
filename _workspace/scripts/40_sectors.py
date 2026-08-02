# -*- coding: utf-8 -*-
"""
40_sectors.py — Sector 1~9 타워 (asset-modeler 산출)

각 섹터 = 기단(Base) + 대형동(Main) + 부속동(Annex) + 창문 스트라이프 4종.
좌표·풋프린트·높이는 전부 spec/track_spec.json 의 sectors 블록에서 읽는다.
여기에 좌표를 하드코딩하면 스펙과 씬이 갈라진다.

생성 오브젝트 (섹터당 7개, 총 63개)
    SEC_01_Base        기단 2단 플린스
    SEC_01_Main        대형동  ← 검수 스크립트가 이 이름으로 좌표를 대조한다
    SEC_01_MainWinA    대형동 ±Y 면 창문 (Array 모디파이어 2단: 열 x 층)
    SEC_01_MainWinB    대형동 ±X 면 창문
    SEC_01_Annex       부속동
    SEC_01_AnnexWinA/B 부속동 창문

창문은 개별 지오메트리로 만들지 않는다. 한 칸짜리 쿼드 2장을 base mesh 로 두고
Array 모디파이어를 열 방향·층 방향으로 두 번 걸어 격자를 만든다. 실제 저장되는
정점은 타워당 8개뿐이라 폴리곤이 폭발하지 않으면서 층수·열수가 건물마다 달라진다.

벽면 세로 홈(리브)은 Main/Annex 메시에 0.0016 m 돌출한 얇은 박스로 넣고, 창문
쿼드는 0.0009 m 만 돌출시킨다. 창이 리브 사이로 들어가 보이는 것이 참조 사진의
세로 스트라이프 룩이다.

부속동 방향: 섹터 1·4·7 은 스펙에 confidence low 로 표시된 추정값이다.
  1 = "대형 + 소형" → 우측(annex_dir R)
  4 = "세로 배치 2동" → 아래쪽이 부속동(annex_dir D)
  7 = "세로 배치 2동" → 아래쪽이 부속동(annex_dir D)
스펙의 annex_dir 를 그대로 따르며, 도면과 대조해 바뀌면 JSON 만 고치면 된다.

--------------------------------------------------------------------------
화재 건물 (spec v1.2.0 fire_buildings) — 파일 하단의 독립 섹션
--------------------------------------------------------------------------
과제3(목표추적)은 9개 건물 중 **불이 난 2개**를 드론·로봇이 찾는 문제다. 스펙의
fire_buildings(섹터 2 intensity 1.0 / 섹터 9 intensity 0.85)에 화재 표현을 얹는다.

  SEC_02_Fire_WinA/WinB       대형동 상부 3개 층 창문을 이미시브 주황으로 덮음
  SEC_02_Fire_AnxWinA/AnxWinB 부속동 상부 2개 층
  SEC_02_Fire_Flame           옥상 화염 (대형동 + 부속동, 단일 메시)
  SEC_02_Fire_Smoke           연기 기둥 (원뿔 스택 — 위로 갈수록 넓고 투명)
  SEC_02_Fire_Light           화염 반사광 POINT (FIRE_LIGHT 로 끌 수 있다)

**기존 타워 생성 로직은 한 줄도 고치지 않았다.** 화재는 위에 덧대는 층이고,
불을 끄고 싶으면 이 섹션만 건너뛰면 원래 건물이 그대로 남는다.

연기를 볼륨 셰이더로 만들지 않은 이유: EEVEE 볼륨은 프레임당 비용이 크고,
반경 0.1 m 스케일에서는 스텝이 성기게 잡혀 거의 보이지 않는다. 반투명 메시
퍼프를 쌓는 편이 훨씬 싸고 오비탈 샷에서 확실히 읽힌다.

화재 부품은 전부 SEC_XX_Main 의 **자식**이다. verify_scene.py 의 겹침 검사와
부유 검사는 `parent is None` 인 것만 보므로, 공중에 뜬 연기가 오탐을 내지 않는다.
"""

import bpy
import bmesh
import math
import os

WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
exec(open(os.path.join(WORKSPACE, "scripts", "00_common.py")).read())

# ---------------------------------------------------------------- 튜닝 파라미터
# 높이를 섹터마다 다르게 주는 것이 오비탈 샷의 스카이라인을 만든다.
# 기본값은 스펙(sectors[n]["h"]). 여기에 넣은 값만 덮어쓴다 — 무작위가 아니라
# 결정적 테이블이라 재실행해도 형태가 같다.
HEIGHT_OVERRIDE = {}

BODY_RATIO = 0.78       # 본체 / 전체 높이 (나머지는 세트백 크라운)
RIB_OUT = 0.0016        # 세로 홈 리브 돌출
WIN_OUT = 0.0009        # 창문 쿼드 돌출 (리브보다 낮아야 홈처럼 보인다)
COL_PITCH = 0.032       # 창문 열 간격 목표
ROW_PITCH = 0.030       # 창문 층 간격 목표
BEVEL_TOWER = 0.0006    # 0.6 mm — 리브 두께(1.6 mm)를 넘지 않게
BEVEL_BASE = 0.0012

# 기단 마진은 우리가 얹은 장식이라 객체와 부딪히면 기단이 물러난다.
# 0 으로 딱 맞추면 부동소수점 오차로 검수가 다시 걸리므로 2 mm 를 남긴다.
BASE_CLEAR = 0.002
BASE_INSET_MAX = 0.014  # 기단이 풋프린트 안쪽으로 물러날 수 있는 한계

DIRS = {"R": (1.0, 0.0), "L": (-1.0, 0.0), "U": (0.0, 1.0), "D": (0.0, -1.0)}


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


def add_quad(g, p0, p1, p2, p3, n=None, mi=0):
    """법선 방향 n 을 지정하면 와인딩을 자동으로 맞춘다 (평면 쿼드는 recalc 대상이 아니다)."""
    pts = [p0, p1, p2, p3]
    if n is not None:
        ux, uy, uz = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
        vx, vy, vz = (p3[0] - p0[0], p3[1] - p0[1], p3[2] - p0[2])
        cx = uy * vz - uz * vy
        cy = uz * vx - ux * vz
        cz = ux * vy - uy * vx
        if cx * n[0] + cy * n[1] + cz * n[2] < 0.0:
            pts = [p0, p3, p2, p1]
    return geo_add(g, pts, [(0, 1, 2, 3)], mi=mi)


def geo_build(name, g, mats, col, loc=(0.0, 0.0, 0.0), bevel=BEVEL_TOWER,
              segments=2, recalc=True):
    """누적 버퍼를 단일 메시 오브젝트로 굽는다. 면별 머티리얼 인덱스/스무딩까지 적용."""
    ob = mesh_object(name, g["v"], g["f"], loc=loc, col=col)
    me = ob.data
    if recalc and len(me.polygons):
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
CONCRETE = SPEC["colors"]["concrete"]
MAT_WALL = get_or_create_material(
    "SEC_Concrete", color=CONCRETE, roughness=0.78, metallic=0.0)
MAT_TRIM = get_or_create_material(
    "SEC_ConcreteLight", color=[c * 1.28 + 0.06 for c in CONCRETE],
    roughness=0.72, metallic=0.0)
MAT_METAL = get_or_create_material(
    "SEC_Metal", color=[0.22, 0.23, 0.25], roughness=0.38, metallic=0.75)
MAT_BASE = get_or_create_material(
    "SEC_Plinth", color=[0.52, 0.52, 0.50], roughness=0.85, metallic=0.0)
# 창문은 두 색을 번갈아 써야 9동이 한 덩어리로 뭉쳐 보이지 않는다.
MAT_WIN_COOL = get_or_create_material(
    "SEC_WindowCool", color=[0.06, 0.08, 0.11], roughness=0.16,
    metallic=0.0, emission=[0.42, 0.58, 0.85], emission_strength=1.7)
MAT_WIN_WARM = get_or_create_material(
    "SEC_WindowWarm", color=[0.10, 0.08, 0.06], roughness=0.16,
    metallic=0.0, emission=[0.95, 0.76, 0.46], emission_strength=1.5)

TOWER_MATS = [MAT_WALL, MAT_TRIM, MAT_METAL]


# ---------------------------------------------------------------- 창문 격자
def win_grid(span):
    """벽면 한 변 길이에서 열 수와 열 간격을 결정론적으로 계산한다."""
    cols = max(2, int(round(span / COL_PITCH)))
    return cols, span / cols


def row_grid(band):
    rows = max(2, int(band / ROW_PITCH))
    return rows, band / rows


def build_windows(name, cx, cy, w, d, zb, zt, mat, col, axis):
    """한 칸 쿼드 2장 + Array 모디파이어 2단으로 창문 격자를 만든다.

    axis='Y' → ±Y 벽면(가로 span=w), axis='X' → ±X 벽면(가로 span=d).
    실제 메시는 쿼드 2장(정점 8개)뿐이고 나머지는 모디파이어가 만든다.
    """
    span = w if axis == 'Y' else d
    cols, pitch = win_grid(span)
    rows, pz = row_grid(max(1e-4, zt - zb))
    ww = pitch * 0.52
    wh = pz * 0.55

    u = -span * 0.5 + pitch * 0.5           # 첫 열 중심
    z = zb + pz * 0.5                       # 첫 층 중심
    a, b = u - ww * 0.5, u + ww * 0.5
    c, e = z - wh * 0.5, z + wh * 0.5

    g = geo_new()
    if axis == 'Y':
        yv = d * 0.5 + WIN_OUT
        add_quad(g, (a, yv, c), (b, yv, c), (b, yv, e), (a, yv, e), n=(0, 1, 0))
        add_quad(g, (a, -yv, c), (b, -yv, c), (b, -yv, e), (a, -yv, e), n=(0, -1, 0))
        step = (pitch, 0.0, 0.0)
    else:
        xv = w * 0.5 + WIN_OUT
        add_quad(g, (xv, a, c), (xv, b, c), (xv, b, e), (xv, a, e), n=(1, 0, 0))
        add_quad(g, (-xv, a, c), (-xv, b, c), (-xv, b, e), (-xv, a, e), n=(-1, 0, 0))
        step = (0.0, pitch, 0.0)

    ob = geo_build(name, g, [mat], col, loc=(cx, cy, 0.0), bevel=None, recalc=False)

    m1 = ob.modifiers.new("ArrayCols", 'ARRAY')
    m1.count = cols
    m1.use_relative_offset = False
    m1.use_constant_offset = True
    m1.constant_offset_displace = step

    m2 = ob.modifiers.new("ArrayRows", 'ARRAY')
    m2.count = rows
    m2.use_relative_offset = False
    m2.use_constant_offset = True
    m2.constant_offset_displace = (0.0, 0.0, pz)

    return ob, cols * rows * 2


# ---------------------------------------------------------------- 타워 지오메트리
def tower_geo(w, d, h, z0):
    """대형동/부속동 공통 실루엣: 본체 + 세트백 크라운 + 옥상 구조물 + 세로 리브.

    z0 = 기단 윗면. 정점은 z0~z0+h+옥상 범위, 오브젝트 원점은 노면(z=0)에 둔다.
    """
    g = geo_new()
    hb = h * BODY_RATIO
    zc = z0 + hb

    add_boxc(g, 0.0, 0.0, z0, w, d, hb, mi=0)                       # 본체
    add_boxc(g, 0.0, 0.0, zc, w * 0.94, d * 0.94, 0.005, mi=1)      # 세트백 슬래브
    zk = zc + 0.005
    hk = max(0.010, z0 + h - zk)
    add_boxc(g, 0.0, 0.0, zk, w * 0.86, d * 0.86, hk, mi=0)         # 크라운
    zr = zk + hk
    add_boxc(g, 0.0, 0.0, zr, w * 0.90, d * 0.90, 0.005, mi=1)      # 옥상 슬래브
    zp = zr + 0.005

    # 옥상 구조물 — 밋밋한 직육면체와 실루엣이 확연히 달라진다
    add_boxc(g, w * 0.16, -d * 0.14, zp, w * 0.34, d * 0.30, h * 0.055, mi=1)
    add_boxc(g, -w * 0.20, d * 0.18, zp, w * 0.24, d * 0.24, h * 0.035, mi=1)
    add_boxc(g, -w * 0.20, d * 0.18, zp + h * 0.035,
             w * 0.11, d * 0.11, h * 0.020, mi=2)
    if h >= 0.44:                                                    # 결정적 변주
        add_cyl(g, (-w * 0.20, d * 0.18, zp + h * 0.055),
                0.0018, h * 0.09, axis='Z', seg=8, mi=2, smooth=True)

    # 세로 홈(리브). 창문 열 경계에 세워 창이 홈 사이로 들어가 보이게 한다.
    cw, pw = win_grid(w)
    cd, pd = win_grid(d)
    rw = min(0.0055, pw * 0.30)
    rd = min(0.0055, pd * 0.30)
    zr0, zr1 = z0 + 0.006, zc + 0.005
    for i in range(cw + 1):
        x = -w * 0.5 + i * pw
        add_box(g, x - rw * 0.5, x + rw * 0.5, -d * 0.5 - RIB_OUT, -d * 0.5, zr0, zr1, mi=1)
        add_box(g, x - rw * 0.5, x + rw * 0.5, d * 0.5, d * 0.5 + RIB_OUT, zr0, zr1, mi=1)
    for i in range(cd + 1):
        y = -d * 0.5 + i * pd
        add_box(g, -w * 0.5 - RIB_OUT, -w * 0.5, y - rd * 0.5, y + rd * 0.5, zr0, zr1, mi=1)
        add_box(g, w * 0.5, w * 0.5 + RIB_OUT, y - rd * 0.5, y + rd * 0.5, zr0, zr1, mi=1)

    # 지상 캐노피 — 발치에 그림자가 생겨 건물이 땅에 붙어 보인다
    add_box(g, -w * 0.24, w * 0.24, -d * 0.5 - 0.013, -d * 0.5,
            z0 + 0.015, z0 + 0.019, mi=1)
    return g


def base_geo(x0, x1, y0, y1, bh):
    """2단 플린스. 한 덩이 박스보다 그림자가 살아 모형처럼 보인다.

    변별로 마진이 달라 중심 대칭이 아니다. 오브젝트 원점은 섹터 pos(스펙 좌표)에
    그대로 두고 로컬 정점만 비대칭으로 만든다 — 원점을 옮기면 검수의 좌표 대조가
    깨진다. SEC_XX_Base 의 location 은 언제나 스펙 pos 다.
    """
    g = geo_new()
    add_box(g, x0, x1, y0, y1, 0.0, bh * 0.6, mi=0)
    ix = min(0.004, (x1 - x0) * 0.15)
    iy = min(0.004, (y1 - y0) * 0.15)
    add_box(g, x0 + ix, x1 - ix, y0 + iy, y1 - iy, bh * 0.6, bh, mi=1)
    return g


# ---------------------------------------------------------------- 객체 충돌 회피
def object_rects():
    """스펙 object_kinds 치수 + yaw 를 반영한 객체 점유 사각형(축정렬 경계).

    회전한 직사각형의 축정렬 반경은  hx = a|cos y| + b|sin y| 다.
    yaw_mode 가 tangential 인 3·17 번도 스펙에 적힌 yaw 를 그대로 쓴다. 방향 무관
    보수 경계(외접원)를 쓰면 SEC_02 기단이 32 mm 나 물러나 부속동이 허공에 걸린다.
    """
    out = []
    for o in SPEC["objects"]:
        kd = SPEC["object_kinds"].get(o["kind"])
        if kd is None:
            continue
        a = float(kd["size"][0]) * 0.5
        b = float(kd["size"][1]) * 0.5
        yaw = float(o.get("yaw", 0.0))
        ca, sa = abs(math.cos(yaw)), abs(math.sin(yaw))
        x, y = o["pos"]
        hx, hy = a * ca + b * sa, a * sa + b * ca
        out.append({"id": int(o["id"]), "kind": o["kind"],
                    "mode": o.get("yaw_mode", "free"),
                    "x0": x - hx, "x1": x + hx, "y0": y - hy, "y1": y + hy})
    return out


OBJ_RECTS = object_rects()


def rect_gap(bx0, bx1, by0, by1, r):
    """사각형 두 개의 여유. 음수면 겹침이고 절댓값이 최소 이동 거리다."""
    return max(max(r["x0"] - bx1, bx0 - r["x1"]),
               max(r["y0"] - by1, by0 - r["y1"]))


def solve_base_margins(px, py, ex, ey, m0):
    """기단 4변의 마진을 객체와 겹치지 않도록 각각 줄인다.

    객체 좌표는 도면 판독값이라 고정이고, 기단은 우리가 얹은 장식이다. 그러니
    기단이 양보한다. 걸리는 객체마다 4방향 후퇴량을 구해 **가장 얕은 방향 한 곳만**
    줄인다 — 네 방향을 다 줄이면 필요 이상으로 기단이 쪼그라든다.

    마진이 음수가 되면 기단이 건물 풋프린트 안으로 물러난다(건물이 살짝 캔틸레버).
    측량 좌표상 객체가 건물 자체와 겹치는 자리가 있어 이걸 허용하지 않으면 해가 없다.
    """
    fx0, fx1 = px - ex, px + ex
    fy0, fy1 = py - ey, py + ey
    bx0, bx1 = fx0 - m0, fx1 + m0
    by0, by1 = fy0 - m0, fy1 + m0
    m = {"x0": m0, "x1": m0, "y0": m0, "y1": m0}
    hits, clipped = [], []
    for r in OBJ_RECTS:
        if not (r["x0"] - BASE_CLEAR < bx1 and r["x1"] + BASE_CLEAR > bx0 and
                r["y0"] - BASE_CLEAR < by1 and r["y1"] + BASE_CLEAR > by0):
            continue
        cand = (("x1", bx1 - (r["x0"] - BASE_CLEAR)),
                ("x0", (r["x1"] + BASE_CLEAR) - bx0),
                ("y1", by1 - (r["y0"] - BASE_CLEAR)),
                ("y0", (r["y1"] + BASE_CLEAR) - by0))
        edge, amt = min(cand, key=lambda t: t[1])
        if m0 - amt < m[edge]:
            m[edge] = m0 - amt
            hits.append((r["id"], r["kind"], r["mode"], edge, amt))
    for k in ("x0", "x1", "y0", "y1"):
        if m[k] < -BASE_INSET_MAX:
            clipped.append((k, m[k]))
            m[k] = -BASE_INSET_MAX          # 기단이 사라지는 것보다는 겹침을 남긴다
    return m, hits, clipped


# ---------------------------------------------------------------- 빌드
purge("SEC_")
COL = link_collection("03_Sectors")

n_obj = 0
n_win = 0
report = []
warns = []
worst_base = (99.0, 0, 0)
worst_tower = (99.0, 0, 0)

for n in range(1, 10):
    sc = sector(n)
    px, py = sc["pos"]
    w, d = sc["foot"]
    h = float(HEIGHT_OVERRIDE.get(n, sc["h"]))
    aw, ad = sc["annex_foot"]
    ah = float(sc["annex_h"])
    he = sc["half_extent"]
    gap = float(sc.get("gap", 0.01))
    bcfg = sc.get("base", {})
    margin = float(bcfg.get("margin", 0.01))
    bh = float(bcfg.get("h", 0.008))

    dv = DIRS.get(sc.get("annex_dir", "R"), (1.0, 0.0))
    axis = 0 if abs(dv[0]) > 0.5 else 1
    main_s = w if axis == 0 else d
    anx_s = aw if axis == 0 else ad
    half = (main_s + gap + anx_s) * 0.5
    mcx = px - dv[0] * (half - main_s * 0.5)
    mcy = py - dv[1] * (half - main_s * 0.5)
    acx = px + dv[0] * (half - anx_s * 0.5)
    acy = py + dv[1] * (half - anx_s * 0.5)

    tag = "SEC_%02d" % n
    win_mat = MAT_WIN_COOL if (n % 2) else MAT_WIN_WARM

    # 기단 — 합친 풋프린트를 margin 만큼 넓게 덮되, 객체와 부딪히는 변만 물러난다
    bm, hits, clipped = solve_base_margins(px, py, he[0], he[1], margin)
    bx0, bx1 = -he[0] - bm["x0"], he[0] + bm["x1"]
    by0, by1 = -he[1] - bm["y0"], he[1] + bm["y1"]
    ob = geo_build(tag + "_Base", base_geo(bx0, bx1, by0, by1, bh),
                   [MAT_BASE, MAT_TRIM], COL, loc=(px, py, 0.0), bevel=BEVEL_BASE)
    ob["base_margin_mm"] = [round(bm[k] * 1000.0, 2) for k in ("x0", "x1", "y0", "y1")]
    n_obj += 1

    for oid, kind, mode, edge, amt in hits:
        inset = margin - amt
        warns.append(
            "  [!] SEC_%02d %s 변 마진 %.1f -> %+.1fmm  (OBJ_%02d %s%s 회피)%s"
            % (n, edge, margin * 1000.0, inset * 1000.0, oid, kind,
               "/tangential" if mode == "tangential" else "",
               "  ← 마진 0 으로도 부족. 객체가 건물 풋프린트 자체와 %.1fmm 겹치므로 "
               "기단을 안쪽으로 넣었고 건물이 그만큼 캔틸레버가 된다 (스펙 이슈)"
               % (-inset * 1000.0) if inset < 0.0 else ""))
    for edge, want in clipped:
        warns.append("  [X] SEC_%02d %s 변: %.1fmm 후퇴가 필요하지만 한계(%.0fmm)에서 잘랐다. "
                     "겹침이 남는다 — 객체 좌표 재검토 필요"
                     % (n, edge, (margin - want) * 1000.0, BASE_INSET_MAX * 1000.0))

    # 대형동 — 검수 스크립트가 이 이름으로 스펙 좌표와 대조한다
    main = geo_build(tag + "_Main", tower_geo(w, d, h, bh), TOWER_MATS, COL,
                     loc=(mcx, mcy, 0.0))
    main["sector"] = n
    main["height"] = h
    n_obj += 1

    hb = h * BODY_RATIO
    zb, zt = bh + 0.020, bh + hb - 0.012
    _, c1 = build_windows(tag + "_MainWinA", mcx, mcy, w, d, zb, zt, win_mat, COL, 'Y')
    _, c2 = build_windows(tag + "_MainWinB", mcx, mcy, w, d, zb, zt, win_mat, COL, 'X')
    n_obj += 2
    n_win += c1 + c2

    # 부속동
    geo_build(tag + "_Annex", tower_geo(aw, ad, ah, bh), TOWER_MATS, COL,
              loc=(acx, acy, 0.0))
    n_obj += 1

    ahb = ah * BODY_RATIO
    azb, azt = bh + 0.014, bh + ahb - 0.010
    _, c3 = build_windows(tag + "_AnnexWinA", acx, acy, aw, ad, azb, azt, win_mat, COL, 'Y')
    _, c4 = build_windows(tag + "_AnnexWinB", acx, acy, aw, ad, azb, azt, win_mat, COL, 'X')
    n_obj += 2
    n_win += c3 + c4

    # ---- 자체 충돌 검사: 기단과 타워(리브·캐노피 포함) 각각의 최소 여유
    gb = min(rect_gap(px + bx0, px + bx1, py + by0, py + by1, r) for r in OBJ_RECTS)
    gb_id = min(OBJ_RECTS, key=lambda r: rect_gap(px + bx0, px + bx1,
                                                  py + by0, py + by1, r))["id"]
    gt, gt_id = 99.0, 0
    for cx, cy, fw, fd in ((mcx, mcy, w, d), (acx, acy, aw, ad)):
        tx0, tx1 = cx - fw * 0.5 - RIB_OUT, cx + fw * 0.5 + RIB_OUT
        ty0, ty1 = cy - fd * 0.5 - 0.013, cy + fd * 0.5 + RIB_OUT   # -Y 는 캐노피
        for r in OBJ_RECTS:
            v = rect_gap(tx0, tx1, ty0, ty1, r)
            if v < gt:
                gt, gt_id = v, r["id"]
    if gb < worst_base[0]:
        worst_base = (gb, n, gb_id)
    if gt < worst_tower[0]:
        worst_tower = (gt, n, gt_id)

    report.append("  SEC_%02d main=(%.3f,%.3f) annex=(%.3f,%.3f) dir=%s | "
                  "기단 마진 -X/+X/-Y/+Y = %+.1f/%+.1f/%+.1f/%+.1f mm | "
                  "최소여유 기단 %+.1fmm(OBJ_%02d) 타워 %+.1fmm(OBJ_%02d)%s"
                  % (n, mcx, mcy, acx, acy, sc.get("annex_dir", "R"),
                     bm["x0"] * 1000.0, bm["x1"] * 1000.0,
                     bm["y0"] * 1000.0, bm["y1"] * 1000.0,
                     gb * 1000.0, gb_id, gt * 1000.0, gt_id,
                     "  [confidence:low]" if sc.get("confidence") == "low" else ""))

for line in report:
    print(line)
for line in warns:
    print(line)

_ok = worst_base[0] >= BASE_CLEAR - 1e-9
print("  충돌검사: 기단 최소여유 %+.2fmm (SEC_%02d vs OBJ_%02d) -> %s  |  "
      "타워 최소여유 %+.2fmm (SEC_%02d vs OBJ_%02d)"
      % (worst_base[0] * 1000.0, worst_base[1], worst_base[2],
         "PASS (>=%.0fmm)" % (BASE_CLEAR * 1000.0) if _ok else "FAIL",
         worst_tower[0] * 1000.0, worst_tower[1], worst_tower[2]))


# =========================================================================
# 화재 건물 — spec v1.2.0 fire_buildings (과제3 목표추적)
#
# 여기서부터는 위의 타워 빌드와 완전히 독립된 "덧대는 층"이다. 위 코드는
# 건드리지 않았고, 아래 블록을 통째로 지워도 원래 건물이 그대로 남는다.
# =========================================================================
from mathutils import Matrix

FIRE_SPEC = SPEC.get("fire_buildings", [])

FIRE_WIN_ROWS_MAIN = 3       # 대형동 최상부 몇 개 층을 불타는 창문으로 덮을지
FIRE_WIN_ROWS_ANNEX = 2
FIRE_WIN_OUT = WIN_OUT + 0.0005   # 기존 창문(WIN_OUT)보다 0.5mm 앞 — Z-파이팅 없이 덮는다

FLAME_H_RATIO = 0.20         # 화염 높이 / 건물 높이
FLAME_TONGUES = 6            # 대형동 옥상 화염 갈래 수
FLAME_TONGUES_ANX = 3

SMOKE_PUFFS = 9
SMOKE_LEVELS = 4             # 투명도 단계 (아래=진하고 불투명, 위=옅고 투명)
SMOKE_H = (0.60, 0.18)       # 연기 높이 = 건물 높이 x (0.60 + 0.18*intensity) → 60~78%
SMOKE_R0 = 0.014             # 기둥 밑동 반경
SMOKE_R1 = (0.052, 0.045)    # 최상부 반경 = 0.052 + 0.045*intensity
SMOKE_LEAN = 0.10            # 상승하며 옆으로 눕는 거리(건물 높이 0.5 기준)
SMOKE_SWAY = 0.018

FIRE_LIGHT = True            # 옥상 화염의 반사광. False 로 두면 이미시브만 남는다
FIRE_LIGHT_POWER = 2.6       # W. LGT_Key(520W AREA)와 비교해 국소적으로만 밝다

# 반투명 셰이딩 방식. EEVEE 세대별로 프로퍼티 이름이 다르므로 둘 다 시도한다.
# 퍼프가 겹치는 구간에서 정렬 아티팩트가 보이면 ('HASHED', 'DITHERED') 로 바꾼다.
SMOKE_BLEND = ('BLEND', 'BLENDED')


def _mat_try(obj, attr, value):
    """버전마다 있고 없는 프로퍼티를 조용히 건너뛴다."""
    if obj is None or not hasattr(obj, attr):
        return False
    try:
        setattr(obj, attr, value)
        return True
    except (AttributeError, TypeError, ValueError):
        return False


def _n01(*keys):
    """결정적 [0,1) 잡음. random 을 쓰면 재실행마다 불꽃 모양이 바뀌어 재현성이 깨진다."""
    v = 0x9E3779B9
    for k in keys:
        v = (v * 1000003 + int(round(float(k) * 977.0))) & 0xFFFFFFFF
        v ^= (v >> 15)
        v = (v * 0x2545F491) & 0xFFFFFFFF
    v ^= (v >> 16)
    return (v & 0xFFFFFF) / float(0x1000000)


def roof_top_z(h, bh):
    """tower_geo 와 **같은 누적 순서**로 옥상 슬래브 윗면 z 를 구한다.

    tower_geo 를 고치면 이 함수도 같이 고쳐야 한다. 값을 하드코딩하지 않고
    같은 식으로 다시 계산하는 이유는, 상수를 두 곳에 두면 반드시 갈라지기 때문이다.
    """
    zc = bh + h * BODY_RATIO
    zk = zc + 0.005
    hk = max(0.010, bh + h - zk)
    return zk + hk + 0.005


def sector_centers(sc):
    """대형동/부속동 중심. 위 빌드 루프와 동일한 계산(스펙에서 재유도)."""
    px, py = sc["pos"]
    w, d = sc["foot"]
    aw, ad = sc["annex_foot"]
    gap = float(sc.get("gap", 0.01))
    dv = DIRS.get(sc.get("annex_dir", "R"), (1.0, 0.0))
    axis = 0 if abs(dv[0]) > 0.5 else 1
    main_s = w if axis == 0 else d
    anx_s = aw if axis == 0 else ad
    half = (main_s + gap + anx_s) * 0.5
    return ((px - dv[0] * (half - main_s * 0.5), py - dv[1] * (half - main_s * 0.5)),
            (px + dv[0] * (half - anx_s * 0.5), py + dv[1] * (half - anx_s * 0.5)))


# ---------------------------------------------------------------- 화재 머티리얼
def fire_materials(n, inten):
    """섹터별 화재 머티리얼 묶음. intensity 가 이미시브 강도와 연기 농도를 지배한다."""
    win = get_or_create_material(
        "SEC_FireWin_%02d" % n, color=[0.16, 0.05, 0.01], roughness=0.22,
        metallic=0.0, emission=[1.0, 0.40, 0.07], emission_strength=4.0 + 9.0 * inten)
    core = get_or_create_material(
        "SEC_FlameCore_%02d" % n, color=[1.0, 0.72, 0.28], roughness=0.9,
        metallic=0.0, emission=[1.0, 0.76, 0.34], emission_strength=8.0 + 24.0 * inten)
    outer = get_or_create_material(
        "SEC_FlameOuter_%02d" % n, color=[0.85, 0.22, 0.03], roughness=0.9,
        metallic=0.0, emission=[1.0, 0.30, 0.04], emission_strength=4.0 + 10.0 * inten)

    smoke = []
    for lv in range(SMOKE_LEVELS):
        t = lv / float(max(1, SMOKE_LEVELS - 1))
        g = 0.09 + 0.30 * t
        alpha = (0.74 - 0.60 * t) * (0.55 + 0.45 * inten)
        # 최하단 퍼프만 불빛을 되받는다 — 연기 밑동이 주황으로 물들면 화재가 훨씬 잘 읽힌다
        em = [0.75, 0.26, 0.05] if lv == 0 else None
        es = 0.9 * inten if lv == 0 else None
        m = get_or_create_material(
            "SEC_Smoke_%02d_L%d" % (n, lv), color=[g, g * 0.97, g * 0.94],
            roughness=0.95, metallic=0.0, emission=em, emission_strength=es)
        bsdf = None
        for nd in m.node_tree.nodes:
            if nd.type == 'BSDF_PRINCIPLED':
                bsdf = nd
                break
        if bsdf is not None:
            _set_input(bsdf, "Alpha", float(alpha))
            _set_input(bsdf, "Specular IOR Level", 0.02)   # 4.x
            _set_input(bsdf, "Specular", 0.02)             # 3.x
        _mat_try(m, "blend_method", SMOKE_BLEND[0])          # 4.1 이하
        _mat_try(m, "shadow_method", 'NONE')
        _mat_try(m, "show_transparent_back", False)
        _mat_try(m, "surface_render_method", SMOKE_BLEND[1])  # 4.2+ EEVEE Next
        _mat_try(m, "use_transparent_shadow", False)
        m.use_backface_culling = True                         # 안쪽 면을 지워 레이어 수를 절반으로
        m.diffuse_color = rgba([g, g, g], alpha)
        smoke.append(m)
    return win, core, outer, smoke


# ---------------------------------------------------------------- 화염 / 연기 지오메트리
def add_flame_tongue(g, base, r, h, seed, tilt=(0.0, 0.0), seg=8):
    """불규칙한 원뿔 한 갈래. 정점을 결정적 잡음으로 흔들어 CG 원뿔 티를 지운다."""
    prof = [(0.00, 1.00), (0.30, 0.88), (0.58, 0.60), (0.82, 0.32)]
    bx, by, bz = base
    v, f, mi = [], [], []
    starts = []
    for ri, (zf, rf) in enumerate(prof):
        ox = bx + tilt[0] * (zf ** 1.6)
        oy = by + tilt[1] * (zf ** 1.6)
        starts.append(len(v))
        for i in range(seg):
            a = 2.0 * math.pi * i / seg
            j = 0.70 + 0.60 * _n01(seed, ri * 3 + 1, i)
            rr = r * rf * j
            zz = bz + h * zf * (0.92 + 0.16 * _n01(seed, i * 5 + 2, ri))
            v.append((ox + rr * math.cos(a), oy + rr * math.sin(a), zz))
    apex = len(v)
    v.append((bx + tilt[0], by + tilt[1], bz + h))
    for b in range(len(prof) - 1):
        s0, s1 = starts[b], starts[b + 1]
        for i in range(seg):
            jn = (i + 1) % seg
            f.append((s0 + i, s0 + jn, s1 + jn, s1 + i))
            mi.append(0 if b < 2 else 1)          # 아래=코어(노랑), 위=바깥(적색)
    sl = starts[-1]
    for i in range(seg):
        f.append((sl + i, sl + (i + 1) % seg, apex))
        mi.append(1)
    f.append(tuple(range(seg - 1, -1, -1)))       # 바닥 캡
    mi.append(0)
    return geo_add(g, v, f, mi=mi, smooth=True)


def flame_cluster(g, cx, cy, z0, r, fh, tongues, seed):
    for i in range(tongues):
        a = 2.0 * math.pi * i / tongues + 0.9 * _n01(seed, i, 11)
        dist = r * (0.10 + 0.62 * _n01(seed, i, 23))
        tx, ty = cx + dist * math.cos(a), cy + dist * math.sin(a)
        th = fh * (0.55 + 0.70 * _n01(seed, i, 37))
        tr = r * (0.20 + 0.22 * _n01(seed, i, 41))
        lean = fh * 0.16
        add_flame_tongue(g, (tx, ty, z0 - 0.002), tr, th, seed * 100 + i,
                         tilt=(lean * (_n01(seed, i, 53) - 0.5),
                               lean * (_n01(seed, i, 59) - 0.5)))
    return g


def add_smoke_puff(g, c, r, seed, mi, seg=10):
    """연기 퍼프 하나 — 위아래로 눌린 회전체를 결정적 잡음으로 찌그러뜨린 덩어리."""
    prof = [(0.00, 0.28), (0.24, 0.72), (0.52, 1.00), (0.78, 0.82), (1.00, 0.30)]
    cx, cy, cz = c
    ph = r * 1.55
    z0 = cz - ph * 0.5
    v, f, starts = [], [], []
    for ri, (zf, rf) in enumerate(prof):
        starts.append(len(v))
        for i in range(seg):
            a = 2.0 * math.pi * i / seg
            jt = 0.80 + 0.42 * _n01(seed, ri * 7 + 3, i)
            rr = r * rf * jt
            v.append((cx + rr * math.cos(a), cy + rr * math.sin(a), z0 + ph * zf))
    bot = len(v)
    v.append((cx, cy, z0 - ph * 0.10))
    top = len(v)
    v.append((cx, cy, z0 + ph * 1.10))
    for b in range(len(prof) - 1):
        s0, s1 = starts[b], starts[b + 1]
        for i in range(seg):
            jn = (i + 1) % seg
            f.append((s0 + i, s0 + jn, s1 + jn, s1 + i))
    s0, sl = starts[0], starts[-1]
    for i in range(seg):
        jn = (i + 1) % seg
        f.append((s0 + jn, s0 + i, bot))
        f.append((sl + i, sl + jn, top))
    return geo_add(g, v, f, mi=mi, smooth=True)


def smoke_column(cx, cy, z0, height, r0, r1, lean_xy, seed):
    """아래에서 위로 갈수록 넓어지고(반경) 옅어지는(머티리얼 인덱스) 퍼프 스택."""
    g = geo_new()
    for p in range(SMOKE_PUFFS):
        t = (p + 0.5) / float(SMOKE_PUFFS)
        z = z0 + height * (t ** 0.92)
        r = r0 + (r1 - r0) * (t ** 0.78)
        sway = SMOKE_SWAY * (_n01(seed, p, 71) - 0.5) * 2.0 * t
        px_ = cx + lean_xy[0] * (t ** 1.35) + sway
        py_ = cy + lean_xy[1] * (t ** 1.35) + sway * 0.6
        lv = min(SMOKE_LEVELS - 1, int(t * SMOKE_LEVELS))
        add_smoke_puff(g, (px_, py_, z), r, seed * 10 + p, lv)
    return g


# ---------------------------------------------------------------- 화재 창문
def build_fire_windows(name, cx, cy, w, d, zb, zt, k_rows, mat, col, axis):
    """build_windows 와 같은 격자 계산을 쓰되 **최상부 k_rows 층만** 만든다.

    기존 build_windows 를 손대지 않기 위해 별도 함수로 둔다. 격자 계산(win_grid /
    row_grid)은 공유하므로 창 위치는 원래 창과 정확히 겹치고, FIRE_WIN_OUT 만큼
    앞으로 나와 있어 아래의 차가운/따뜻한 창을 가린다.
    """
    span = w if axis == 'Y' else d
    cols, pitch = win_grid(span)
    rows, pz = row_grid(max(1e-4, zt - zb))
    k = max(1, min(rows, int(k_rows)))
    ww, wh = pitch * 0.52, pz * 0.55
    u = -span * 0.5 + pitch * 0.5
    z = zb + pz * (rows - k) + pz * 0.5
    a, b = u - ww * 0.5, u + ww * 0.5
    c, e = z - wh * 0.5, z + wh * 0.5

    g = geo_new()
    if axis == 'Y':
        yv = d * 0.5 + FIRE_WIN_OUT
        add_quad(g, (a, yv, c), (b, yv, c), (b, yv, e), (a, yv, e), n=(0, 1, 0))
        add_quad(g, (a, -yv, c), (b, -yv, c), (b, -yv, e), (a, -yv, e), n=(0, -1, 0))
        step = (pitch, 0.0, 0.0)
    else:
        xv = w * 0.5 + FIRE_WIN_OUT
        add_quad(g, (xv, a, c), (xv, b, c), (xv, b, e), (xv, a, e), n=(1, 0, 0))
        add_quad(g, (-xv, a, c), (-xv, b, c), (-xv, b, e), (-xv, a, e), n=(-1, 0, 0))
        step = (0.0, pitch, 0.0)

    ob = geo_build(name, g, [mat], col, loc=(cx, cy, 0.0), bevel=None, recalc=False)
    m1 = ob.modifiers.new("ArrayCols", 'ARRAY')
    m1.count = cols
    m1.use_relative_offset = False
    m1.use_constant_offset = True
    m1.constant_offset_displace = step
    m2 = ob.modifiers.new("ArrayRows", 'ARRAY')
    m2.count = k
    m2.use_relative_offset = False
    m2.use_constant_offset = True
    m2.constant_offset_displace = (0.0, 0.0, pz)
    return ob, cols * k * 2


# ---------------------------------------------------------------- 화재 빌드
n_fire_obj = 0
fire_lines = []

for fb in FIRE_SPEC:
    n = int(fb.get("sector", 0))
    inten = max(0.0, min(1.0, float(fb.get("intensity", 1.0))))
    sc = SPEC["sectors"].get(str(n))
    main_ob = bpy.data.objects.get("SEC_%02d_Main" % n)
    if sc is None or main_ob is None:
        print("  [!] fire_buildings: 섹터 %s 를 찾지 못해 화재를 건너뛴다" % n)
        continue

    w, d = sc["foot"]
    aw, ad = sc["annex_foot"]
    h = float(HEIGHT_OVERRIDE.get(n, sc["h"]))
    ah = float(sc["annex_h"])
    bh = float(sc.get("base", {}).get("h", 0.008))
    (mcx, mcy), (acx, acy) = sector_centers(sc)

    tag = "SEC_%02d_Fire" % n
    M_WIN, M_CORE, M_OUT, M_SMOKE = fire_materials(n, inten)
    # 부모의 로컬 좌표계로 들어가지 않도록 부모 위치의 역이동을 넣는다.
    # 이러면 자식의 location 을 월드 좌표 그대로 쓸 수 있다 (55_placement 의 체크포인트와 동일 수법).
    pinv = Matrix.Translation((-mcx, -mcy, 0.0))
    children = []

    # 1) 상부 층 창문을 화염색으로 — 멀리서도 "이 동이 탄다"가 읽히는 가장 싼 신호
    hb = h * BODY_RATIO
    zb, zt = bh + 0.020, bh + hb - 0.012
    ob, c1 = build_fire_windows(tag + "_WinA", mcx, mcy, w, d, zb, zt,
                                FIRE_WIN_ROWS_MAIN, M_WIN, COL, 'Y')
    children.append(ob)
    ob, c2 = build_fire_windows(tag + "_WinB", mcx, mcy, w, d, zb, zt,
                                FIRE_WIN_ROWS_MAIN, M_WIN, COL, 'X')
    children.append(ob)

    ahb = ah * BODY_RATIO
    azb, azt = bh + 0.014, bh + ahb - 0.010
    ob, c3 = build_fire_windows(tag + "_AnxWinA", acx, acy, aw, ad, azb, azt,
                                FIRE_WIN_ROWS_ANNEX, M_WIN, COL, 'Y')
    children.append(ob)
    ob, c4 = build_fire_windows(tag + "_AnxWinB", acx, acy, aw, ad, azb, azt,
                                FIRE_WIN_ROWS_ANNEX, M_WIN, COL, 'X')
    children.append(ob)

    # 2) 옥상 화염 — 대형동과 부속동을 한 메시에 담는다 (오브젝트 수를 늘리지 않는다)
    mz = roof_top_z(h, bh)
    az = roof_top_z(ah, bh)
    fh = h * FLAME_H_RATIO * (0.75 + 0.25 * inten)
    gfl = geo_new()
    flame_cluster(gfl, 0.0, 0.0, mz, min(w, d) * 0.40, fh, FLAME_TONGUES, n * 7 + 1)
    flame_cluster(gfl, acx - mcx, acy - mcy, az, min(aw, ad) * 0.40, fh * 0.62,
                  FLAME_TONGUES_ANX, n * 7 + 2)
    flame = geo_build(tag + "_Flame", gfl, [M_CORE, M_OUT], COL,
                      loc=(mcx, mcy, 0.0), bevel=None)
    _mat_try(flame, "visible_shadow", False)   # 이미시브가 그림자를 드리우면 옥상이 시커멓게 죽는다
    children.append(flame)

    # 3) 연기 기둥 — 아레나 바깥쪽(±Y)으로 눕혀 드론 웨이포인트와 겹치지 않게 한다
    sh = h * (SMOKE_H[0] + SMOKE_H[1] * inten)
    sr1 = SMOKE_R1[0] + SMOKE_R1[1] * inten
    ly = 1.0 if sc["pos"][1] >= 0.0 else -1.0
    lean = (SMOKE_LEAN * (h / 0.5) * 0.25 * (_n01(n, 3) - 0.5) * 2.0,
            SMOKE_LEAN * (h / 0.5) * ly)
    gsm = smoke_column(0.0, 0.0, mz + fh * 0.55, sh, SMOKE_R0, sr1, lean, n * 13 + 5)
    smoke = geo_build(tag + "_Smoke", gsm, M_SMOKE, COL, loc=(mcx, mcy, 0.0), bevel=None)
    _mat_try(smoke, "visible_shadow", False)   # 반투명 메시의 그림자는 얼룩으로만 보인다
    children.append(smoke)

    # 4) 화염 반사광 — 옥상 구조물과 이웃 벽면에 주황 하이라이트를 남긴다
    if FIRE_LIGHT:
        lname = tag + "_Light"
        ld = bpy.data.lights.get(lname)     # 이름으로 재사용 (purge 는 오브젝트만 지운다)
        if ld is None:
            ld = bpy.data.lights.new(lname, 'POINT')
        ld.type = 'POINT'
        ld.color = (1.0, 0.45, 0.13)
        ld.energy = FIRE_LIGHT_POWER * inten
        _mat_try(ld, "shadow_soft_size", 0.05)
        _mat_try(ld, "use_shadow", False)   # 그림자 계산을 아껴 프레임 비용을 낮춘다
        lo = bpy.data.objects.new(lname, ld)
        link_to(lo, COL)
        lo.location = (mcx, mcy, mz + fh * 0.5)
        children.append(lo)

    for ch in children:
        ch.parent = main_ob
        ch.matrix_parent_inverse = pinv.copy()
    n_fire_obj += len(children)

    fire_lines.append(
        "  SEC_%02d 화재  intensity=%.2f | 화염창 %d칸(대형 상단 %d층 / 부속 %d층) | "
        "옥상 z=%.3f 화염 h=%.3f | 연기 h=%.3f (건물 h=%.2f 의 %.0f%%) 최대반경 %.3f "
        "lean=(%+.3f,%+.3f) | 연기 정점 z=%.3f"
        % (n, inten, c1 + c2 + c3 + c4, FIRE_WIN_ROWS_MAIN, FIRE_WIN_ROWS_ANNEX,
           mz, fh, sh, h, sh / h * 100.0, sr1, lean[0], lean[1],
           mz + fh * 0.55 + sh))

for line in fire_lines:
    print(line)
if FIRE_SPEC and not fire_lines:
    print("  [!] fire_buildings 스펙은 있는데 화재를 하나도 만들지 못했다 — 섹터 번호 확인")

print("[40_sectors] built %d objects in 03_Sectors (sectors=9, windows=%d via Array) "
      "| tallest=%.2fm shortest=%.2fm | base-object clearance %s "
      "| fire=%d동 %d오브젝트 (%s)"
      % (len(COL.objects), n_win,
         max(sector(i)["h"] for i in range(1, 10)),
         min(sector(i)["h"] for i in range(1, 10)),
         "OK" if _ok else "VIOLATION",
         len(fire_lines), n_fire_obj,
         "/".join("SEC_%02d" % int(f["sector"]) for f in FIRE_SPEC) or "none"))
