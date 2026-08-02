# -*- coding: utf-8 -*-
"""
20_markings.py — 도로 마킹 (track-builder)

차선 구조 (SPEC v1.2.1 lanes.interpretation)
    lanes 의 outer / sub_loops[] 의 min/max/r 은 **블록(건물 구역) 외곽선**이고
    노란 선은 그 위에 한 줄로 그려진다. 인접 블록 사이의 간격이 곧 도로다.
    별도의 도로 폭 오프셋(±road_width/2)을 주면 도로가 블록 안으로 파고든다.

    근거 (v1.2.0 의 '도로 중심선' 해석을 폐기한 이유):
      A.max.x 0.44 ↔ B.min.x 0.68 중점 0.56 = 독립 판독된 cross_lines.v_x
      A.min.y 0.31 ↔ D.max.y 0.05 중점 0.18 = cross_lines.h_y
      outer.max.x 2.41 ↔ B.max.x 2.08 중점 2.245 = lanes.cross_check 값

생성물 (전부 01_Markings / MRK_ 접두사, Z = SPEC.road.line_z = 0.5 mm)
    MRK_Lane_Outer             노란 외곽 순환로   (베지어, 닫힌 라운드 사각)
    MRK_Lane_A ~ _E            노란 블록 외곽선 5개 (베지어, 닫힌 라운드 사각)
    MRK_Line_CrossV/_H         흰 십자 교차로 **실선** (블록을 지나는 구간에서 끊김)
    MRK_Start_Line             흰 출발선
    MRK_Start_Bracket          흰 사각 브래킷 4모서리
    MRK_Finish_Band            노랑/검정 사선 밴드
    MRK_Helipad_Pad/_Ring/_H   검정 판 + 주황 링 + 흰 H

곡선을 베지어로 만드는 이유
    폴리곤을 손으로 깔면 "차선 좀 왼쪽으로" 한마디에 전량 재작업이다. 베지어는
    제어점 8개만 옮기면 되고, 그 제어점이 SPEC.lanes 의 min/max/r 에서 기계적으로
    유도되므로 스펙 한 줄만 고치면 전부 따라온다.

흰 선만 Z 를 0.1 mm 올리는 이유
    십자 실선 두 줄은 (0.56, 0.18) 에서 서로 겹치고, 노란 선과도 교차할 수 있다.
    같은 Z 면 그 교차점에서 Z-파이팅이 나 렌더가 얼룩진다. 0.0005 / 0.0006 으로 나눈다.

리본 두께
    커브에 bevel_depth 를 주면 단면이 원통이라 노면 아래로 파고든다. 오브젝트
    Z 스케일을 RIBBON_FLAT 으로 눌러 납작한 도장선으로 만든다. 커브 제어점은
    로컬 z=0 에 두고 오브젝트 원점을 line_z 에 올리므로, 리본은 항상
    line_z ± (line_w/2 * RIBBON_FLAT) 안에 들어간다 (균열 데칼 0.3 mm 보다 위).

주의 — SPEC.lanes 는 confidence: medium, 좌표는 track-surveyor 소관
    스펙이 어긋나면 여기서 클램프하지 않고 ISSUES 로 보고만 한다. 조용히 자르면
    "왜 도면과 다른가"의 원인이 스크립트 안에 숨는다.
"""

import bpy
import math
import os

WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
exec(open(os.path.join(WORKSPACE, "scripts", "00_common.py")).read())

# ---------------------------------------------------------------- 튜닝 상수
_LN = SPEC.get("lanes") or {}
_CL = _LN.get("cross_lines") or {}

LANE_W = float(SPEC["road"]["line_w"])           # 노란 차선 폭 (0.015)
WHITE_W = float(_CL.get("width", 0.012))         # 흰 십자선 폭 (0.012)
CROSS_SOLID = str(_CL.get("style", "solid")).lower() == "solid"

RIBBON_FLAT = 0.02                               # 커브 리본 납작 비율
DASH_LEN, DASH_GAP = 0.09, 0.06                  # style != solid 일 때만 쓰는 파선 피치
BREAK_PAD = 0.02                                 # 십자선을 블록 경계 밖으로 더 끊는 여유
MIN_SEG = 0.03                                   # 이보다 짧은 흰 선 조각은 버린다 (점처럼 보임)

Z_MARK = LINE_Z                                  # 0.0005 — 노란 차선
Z_WHITE = LINE_Z + 0.0001                        # 0.0006 — 흰 선 (교차점 Z-파이팅 회피)
Z_OVER = LINE_Z + 0.0002                         # 헬리패드 링/H (허용 오차 ±0.0002 내)
Z_UNDER = LINE_Z - 0.0001                        # 헬리패드 검정 판 (링보다 아래)
K = 0.5522847498307936                           # 사분원 베지어 핸들 계수

MISSING = []
ISSUES = []
LANE_RECTS = []     # (name, (x0,y0,x1,y1,r), is_block) — 노란 선 사각 목록
OVERRUN = []        # 건물 풋프린트가 노란 선을 밟은 목록
CROSS_IN_BLOCK = [] # 흰 십자선이 블록 내부를 지난 목록
BOUND_MAX = [0.0, 0.0]   # 지금까지 만든 마킹의 max|x|, max|y| (리본 반폭 포함)

C = SPEC["colors"]


# ---------------------------------------------------------------- 머티리얼
def reset_material_nodes(name):
    mat = get_or_create_material(name)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (620, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (320, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat, nt, bsdf


def build_stripe_material(name="MAT_HazardStripe", scale=16.0):
    """노랑/검정 45° 사선. 지오메트리로 깎지 않고 Wave 텍스처로 만든다.

    30_hazards 의 배리어도 같은 이름의 머티리얼을 쓴다. 두 스크립트가 각자
    이 함수를 갖고 있어 실행 순서와 무관하게 자기 완결적으로 돌아간다.
    스트라이프 간격 ≈ 0.3/scale m — 굵기 조정은 scale 한 곳만 만진다.
    """
    mat, nt, bsdf = reset_material_nodes(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-620, 0)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.location = (-420, 0)
    for attr, val in (("wave_type", 'BANDS'), ("bands_direction", 'DIAGONAL'),
                      ("wave_profile", 'SIN')):
        try:
            setattr(wave, attr, val)
        except Exception:
            pass
    _set_input(wave, "Scale", scale)
    _set_input(wave, "Distortion", 0.0)
    _set_input(wave, "Detail", 0.0)
    nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])

    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-180, 0)
    cr = ramp.color_ramp
    cr.interpolation = 'CONSTANT'                # 하드 엣지 사선
    cr.elements[0].position = 0.0
    cr.elements[0].color = rgba(C["hazard_black"])
    cr.elements[1].position = 0.5
    cr.elements[1].color = rgba(C["hazard_yellow"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _set_input(bsdf, "Roughness", 0.45)
    _set_input(bsdf, "Metallic", 0.0)
    mat.diffuse_color = rgba(C["hazard_yellow"])
    return mat


# ---------------------------------------------------------------- 커브 헬퍼
def rrect_points(x0, y0, x1, y1, r):
    """반시계 방향 라운드 사각의 베지어 제어점 8개.

    직선 구간은 VECTOR 핸들(자동으로 완전한 직선), 코너는 FREE 핸들에
    사분원 계수 K 를 넣어 정확한 원호를 만든다. AUTO 로 두면 코너가 부풀어
    스펙의 코너 반경 r 이 무의미해진다.
    """
    rmax = min((x1 - x0), (y1 - y0)) * 0.5
    if r > rmax + 1e-9:
        ISSUES.append("코너 반경 r=%.3f 이 사각(%.2f,%.2f)-(%.2f,%.2f) 의 한계 %.3f 초과"
                      % (r, x0, y0, x1, y1, rmax))
        r = rmax
    P = []

    def pt(co, hl, hlt, hr, hrt):
        P.append({"co": co, "hl": hl, "hlt": hlt, "hr": hr, "hrt": hrt})

    if r < 1e-6:
        # r=0 을 8점 경로로 만들면 제어점이 쌍쌍이 겹쳐 bevel 단면이 뒤집힌다.
        # 안쪽 경계선(r-0.15 가 0 으로 클램프된 경우)이 여기로 온다.
        for co in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            pt(co, None, 'VECTOR', None, 'VECTOR')
        return P

    k = r * K
    pt((x0 + r, y0), (x0 + r - k, y0), 'FREE', None, 'VECTOR')          # 하단 시작
    pt((x1 - r, y0), None, 'VECTOR', (x1 - r + k, y0), 'FREE')          # 하단 끝
    pt((x1, y0 + r), (x1, y0 + r - k), 'FREE', None, 'VECTOR')          # 우측 시작
    pt((x1, y1 - r), None, 'VECTOR', (x1, y1 - r + k), 'FREE')          # 우측 끝
    pt((x1 - r, y1), (x1 - r + k, y1), 'FREE', None, 'VECTOR')          # 상단 시작
    pt((x0 + r, y1), None, 'VECTOR', (x0 + r - k, y1), 'FREE')          # 상단 끝
    pt((x0, y1 - r), (x0, y1 - r + k), 'FREE', None, 'VECTOR')          # 좌측 시작
    pt((x0, y0 + r), None, 'VECTOR', (x0, y0 + r - k), 'FREE')          # 좌측 끝
    return P


def make_lane_curve(name, pts, width, closed=True, mat=None, col="01_Markings",
                    z=Z_MARK, res=12):
    cu = bpy.data.curves.new(name + "_crv", 'CURVE')
    cu.dimensions = '3D'
    cu.resolution_u = res
    cu.bevel_depth = width * 0.5
    cu.bevel_resolution = 2
    cu.fill_mode = 'FULL'
    cu.use_fill_caps = True

    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = (p["co"][0], p["co"][1], 0.0)
    for bp, p in zip(sp.bezier_points, pts):
        bp.handle_left_type = p.get("hlt", 'AUTO')
        bp.handle_right_type = p.get("hrt", 'AUTO')
        if p.get("hl") is not None:
            bp.handle_left = (p["hl"][0], p["hl"][1], 0.0)
        if p.get("hr") is not None:
            bp.handle_right = (p["hr"][0], p["hr"][1], 0.0)
    sp.use_cyclic_u = bool(closed)

    ob = bpy.data.objects.new(name, cu)
    ob.location = (0.0, 0.0, z)
    ob.scale = (1.0, 1.0, RIBBON_FLAT)      # 원통 단면 → 납작한 도장선
    link_to(ob, col)
    if mat is not None:
        set_material(ob, mat)
    check_bounds(name, [p["co"] for p in pts], pad=width * 0.5)
    return ob


def check_bounds(name, pts, pad=0.0):
    """경기장 밖으로 나가면 클램프하지 않고 보고한다. 조용히 자르면 원인이 숨는다.

    pad 는 리본 반폭 — 제어점이 경계 안이라도 선 두께가 넘칠 수 있다.
    """
    ok = True
    for x, y in pts:
        ax, ay = abs(x) + pad, abs(y) + pad
        BOUND_MAX[0] = max(BOUND_MAX[0], ax)
        BOUND_MAX[1] = max(BOUND_MAX[1], ay)
        if ok and (ax > ARENA_W * 0.5 + 1e-6 or ay > ARENA_H * 0.5 + 1e-6):
            ISSUES.append("%s 가 경기장(±%.2f, ±%.2f) 이탈: (%.3f, %.3f) 폭 포함 (%.4f, %.4f)"
                          % (name, ARENA_W * 0.5, ARENA_H * 0.5, x, y, ax, ay))
            ok = False
    return ok


# ---------------------------------------------------------------- 평면 헬퍼
class Quads(object):
    """여러 사각형을 메시 하나로 모은다 (오브젝트 수를 늘리지 않는다)."""

    def __init__(self):
        self.verts = []
        self.faces = []

    def rect(self, x0, y0, x1, y1):
        i = len(self.verts)
        self.verts += [(x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0)]
        self.faces.append((i, i + 1, i + 2, i + 3))

    def quad(self, p0, p1, p2, p3):
        i = len(self.verts)
        self.verts += [(p0[0], p0[1], 0.0), (p1[0], p1[1], 0.0),
                       (p2[0], p2[1], 0.0), (p3[0], p3[1], 0.0)]
        self.faces.append((i, i + 1, i + 2, i + 3))

    def build(self, name, z=Z_MARK, mat=None, col="01_Markings"):
        return mesh_object(name, self.verts, self.faces, (0.0, 0.0, z), col, mat)


def dashed_line(name, p0, p1, w, mat, skip=(), z=Z_MARK, dash=DASH_LEN, gap=DASH_GAP):
    """양 끝이 딱 떨어지도록 피치를 재분배한 파선. skip=[(x,y,r)] 구간은 건너뛴다."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy)
    if L < 1e-6:
        ISSUES.append("%s 길이가 0" % name)
        return None
    ux, uy = dx / L, dy / L
    nx, ny = -uy * w * 0.5, ux * w * 0.5
    n = max(1, int(round((L + gap) / (dash + gap))))
    pitch = (L + gap) / n
    d = pitch - gap

    q = Quads()
    for i in range(n):
        s0 = i * pitch
        s1 = s0 + d
        mx, my = p0[0] + ux * (s0 + s1) * 0.5, p0[1] + uy * (s0 + s1) * 0.5
        if any(math.hypot(mx - sx, my - sy) < sr for sx, sy, sr in skip):
            continue
        a = (p0[0] + ux * s0, p0[1] + uy * s0)
        b = (p0[0] + ux * s1, p0[1] + uy * s1)
        q.quad((a[0] - nx, a[1] - ny), (b[0] - nx, b[1] - ny),
               (b[0] + nx, b[1] + ny), (a[0] + nx, a[1] + ny))
    check_bounds(name, [p0, p1], pad=w * 0.5)
    return q.build(name, z, mat)


def solid_line(name, axis, coord, segs, w, mat, z=Z_WHITE):
    """축 정렬 실선을 구간 목록으로 만든다. axis='V' 면 x=coord, 'H' 면 y=coord."""
    if not segs:
        ISSUES.append("%s 이 도로 구간에 전부 먹혀 사라졌다 — lanes 좌표 재검토 필요" % name)
        return None
    q, pts = Quads(), []
    for s0, s1 in segs:
        if axis == 'V':
            q.rect(coord - w * 0.5, s0, coord + w * 0.5, s1)
            pts += [(coord, s0), (coord, s1)]
        else:
            q.rect(s0, coord - w * 0.5, s1, coord + w * 0.5)
            pts += [(s0, coord), (s1, coord)]
    check_bounds(name, pts, pad=w * 0.5)
    return q.build(name, z, mat)


def make_ring(name, r_out, r_in, cx, cy, z, mat, seg=64, col="01_Markings"):
    verts, faces = [], []
    for k in range(seg):
        a = 2.0 * math.pi * k / seg
        verts.append((cx + r_out * math.cos(a), cy + r_out * math.sin(a), 0.0))
    for k in range(seg):
        a = 2.0 * math.pi * k / seg
        verts.append((cx + r_in * math.cos(a), cy + r_in * math.sin(a), 0.0))
    for k in range(seg):
        j = (k + 1) % seg
        faces.append((k, j, seg + j, seg + k))
    return mesh_object(name, verts, faces, (0.0, 0.0, z), col, mat)


# ---------------------------------------------------------------- 차선 조립
def build_lane(key, rect, closed=True, is_block=True):
    """블록 외곽선 하나를 노란 차선 한 줄로 그린다.

    lanes.interpretation 대로 min/max/r 이 곧 노란 선의 경로다. 오프셋을 주지
    않는다 — 도로는 인접 블록 사이의 '간격'이지 선의 폭이 아니다.
    LANE_RECTS 에 남겨 십자선 끊기·건물 침범 검사가 같은 좌표를 재사용한다.
    """
    make_lane_curve("MRK_Lane_%s" % key, rrect_points(*rect),
                    LANE_W, closed=closed, mat=mat_yellow, z=Z_MARK)
    LANE_RECTS.append((key, rect, bool(is_block)))
    return LANE_RECTS[-1]


def block_cuts(axis, coord, pad=BREAK_PAD):
    """십자 실선이 블록 사각 내부를 지나는 구간 목록 — 여기서 흰 선을 끊는다.

    흰 십자선은 블록 **사이의 도로**를 달리는 선이라 블록 안을 가로지르면 안 된다.
    외곽 순환로(is_block=False)는 제외한다 — 십자선은 항상 그 안에 있어서
    포함시키면 선이 통째로 지워진다.
    """
    cuts = []
    for _name, (x0, y0, x1, y1, _r), is_block in LANE_RECTS:
        if not is_block:
            continue
        if axis == 'V':
            if x0 - pad <= coord <= x1 + pad:
                cuts.append((y0 - pad, y1 + pad))
        else:
            if y0 - pad <= coord <= y1 + pad:
                cuts.append((x0 - pad, x1 + pad))
    return cuts


def subtract_intervals(lo, hi, cuts, min_len=MIN_SEG):
    """[lo,hi] 에서 cuts 구간을 빼고 min_len 이상인 조각만 남긴다."""
    segs = [(lo, hi)]
    for c0, c1 in cuts:
        a, b = (c0, c1) if c0 <= c1 else (c1, c0)
        nxt = []
        for s0, s1 in segs:
            if b <= s0 or a >= s1:
                nxt.append((s0, s1))
                continue
            if s0 < a - 1e-9:
                nxt.append((s0, a))
            if b + 1e-9 < s1:
                nxt.append((b, s1))
        segs = nxt
    return [s for s in segs if s[1] - s[0] >= min_len]


# ---------------------------------------------------------------- 검수 보조
def check_sector_clearance():
    """건물 풋프린트가 노란 선을 밟는지 본다 (블록 경계선이므로 침범 0 이 정상).

    asset-modeler 의 건물과 이 차선이 겹치면 검수에서 잡힌다. 여기서 미리 알려
    "누가 먼저 움직여야 하는가"를 명확히 한다. 고치지는 않는다.
    """
    e = LANE_W * 0.5                                       # 선 반폭까지 여유로 본다
    for key in sorted(SPEC.get("sectors", {}), key=lambda k: int(k)):
        s = SPEC["sectors"][key]
        hx, hy = s.get("half_extent", [0.1, 0.1])
        bx0, by0 = s["pos"][0] - hx - e, s["pos"][1] - hy - e
        bx1, by1 = s["pos"][0] + hx + e, s["pos"][1] + hy + e
        for name, (lx0, ly0, lx1, ly1, _r), _is_block in LANE_RECTS:
            if bx1 <= lx0 or bx0 >= lx1 or by1 <= ly0 or by0 >= ly1:
                continue                                   # 이 사각과 무관
            if bx0 >= lx0 and bx1 <= lx1 and by0 >= ly0 and by1 <= ly1:
                continue                                   # 블록 내부 = 정상
            d = max(lx0 - bx0, bx1 - lx1, ly0 - by0, by1 - ly1)
            OVERRUN.append((key, name, d))


def check_cross_in_block(axis, coord, segs):
    """만들어진 흰 십자선 조각이 블록 사각 내부를 지나는지 사후 확인한다.

    block_cuts 가 제 일을 했는지 '결과물'로 검산한다. 끊기 로직과 검사 로직이
    같은 식을 공유하면 둘 다 틀려도 통과하므로, 여기서는 pad 없이 순수 포함만 본다.
    """
    for name, (x0, y0, x1, y1, _r), is_block in LANE_RECTS:
        if not is_block:
            continue
        for s0, s1 in segs:
            if axis == 'V':
                if not (x0 < coord < x1):
                    continue
                ov = min(s1, y1) - max(s0, y0)
            else:
                if not (y0 < coord < y1):
                    continue
                ov = min(s1, x1) - max(s0, x0)
            if ov > 1e-6:
                CROSS_IN_BLOCK.append((axis, name, ov))


def corner_report():
    """코너 반경이 도면과 맞는지 판단할 근거를 숫자로 남긴다.

    렌더 없이 '각져 보이는가'는 알 수 없으므로, 짧은 변 대비 반경 비율을 낸다.
    외곽 순환로와 서브 루프의 비율이 크게 어긋나면 도면과 대조할 근거가 된다.
    """
    rows = []
    for name, (x0, y0, x1, y1, r), _is_block in LANE_RECTS:
        short = min(x1 - x0, y1 - y0)
        rows.append((name, r, short, r / short if short > 1e-9 else 0.0))
    return rows


# ---------------------------------------------------------------- 실행
purge("MRK_")
col = link_collection("01_Markings")

mat_yellow = get_or_create_material("MAT_LaneYellow", color=C["lane_yellow"],
                                    roughness=0.55, metallic=0.0)
mat_white = get_or_create_material("MAT_LineWhite", color=C["line_white"],
                                   roughness=0.58, metallic=0.0)
mat_black = get_or_create_material("MAT_PadBlack", color=C["hazard_black"],
                                   roughness=0.72, metallic=0.0)
mat_ring = get_or_create_material("MAT_HelipadRing", color=C["helipad_ring"],
                                  roughness=0.5, metallic=0.0)
mat_stripe = build_stripe_material()

LANES = SPEC.get("lanes")
if LANES is None:
    MISSING.append("lanes (차선 폴리라인) — 마킹 생성 불가")
    LANES = {"outer": {"min": [-2.41, -1.71], "max": [2.41, 1.71], "r": 0.32},
             "sub_loops": [], "cross_v": None, "cross_h": None}
if LANES.get("confidence") in ("low", "medium"):
    MISSING.append("lanes.confidence=%s — 톱 뷰 대조 후 min/max/r 조정 예상"
                   % LANES.get("confidence"))
if not _CL:
    MISSING.append("lanes.cross_lines — 폭 %.3f / 실선 으로 가정" % WHITE_W)

# 1) 노란 차선 — 외곽 순환로 + 블록 외곽선 5개. 오프셋 없이 사각 위에 한 줄씩.
o = LANES["outer"]
build_lane("Outer",
           (float(o["min"][0]), float(o["min"][1]),
            float(o["max"][0]), float(o["max"][1]), float(o.get("r", 0.32))),
           closed=bool(o.get("closed", True)), is_block=False)

for lp in LANES.get("sub_loops", []):
    build_lane(str(lp["name"]),
               (float(lp["min"][0]), float(lp["min"][1]),
                float(lp["max"][0]), float(lp["max"][1]), float(lp.get("r", 0.10))),
               closed=True, is_block=True)

# 2) 십자 교차로 — 흰 **실선**. 블록 내부를 지나는 구간에서만 끊는다.
cv, ch = LANES.get("cross_v"), LANES.get("cross_h")
cx = float(_CL.get("v_x", cv["x"] if cv else SPEC["road"]["cross"]["x"]))
cy = float(_CL.get("h_y", ch["y"] if ch else SPEC["road"]["cross"]["y"]))
if cv and abs(float(cv["x"]) - cx) > 1e-6:
    ISSUES.append("lanes.cross_v.x(%.3f) 와 cross_lines.v_x(%.3f) 불일치" % (cv["x"], cx))
if ch and abs(float(ch["y"]) - cy) > 1e-6:
    ISSUES.append("lanes.cross_h.y(%.3f) 와 cross_lines.h_y(%.3f) 불일치" % (ch["y"], cy))

if cv:
    v_cuts = block_cuts('V', cx)
    # 세로선이 가로선을 '지나가게' 한다 — 둘 다 Z_WHITE 라 겹치면 Z-파이팅.
    v_cuts.append((cy - WHITE_W * 0.5 - 0.005, cy + WHITE_W * 0.5 + 0.005))
    v_segs = subtract_intervals(float(cv["y0"]), float(cv["y1"]), v_cuts)
    if CROSS_SOLID:
        solid_line("MRK_Line_CrossV", 'V', cx, v_segs, WHITE_W, mat_white)
    else:
        for i, (s0, s1) in enumerate(v_segs):
            dashed_line("MRK_Line_CrossV_%d" % i, (cx, s0), (cx, s1),
                        WHITE_W, mat_white, z=Z_WHITE)
    check_cross_in_block('V', cx, v_segs)
else:
    v_segs = []
    MISSING.append("lanes.cross_v")

if ch:
    h_segs = subtract_intervals(float(ch["x0"]), float(ch["x1"]), block_cuts('H', cy))
    if CROSS_SOLID:
        solid_line("MRK_Line_CrossH", 'H', cy, h_segs, WHITE_W, mat_white)
    else:
        for i, (s0, s1) in enumerate(h_segs):
            dashed_line("MRK_Line_CrossH_%d" % i, (s0, cy), (s1, cy),
                        WHITE_W, mat_white, z=Z_WHITE)
    check_cross_in_block('H', cy, h_segs)
else:
    h_segs = []
    MISSING.append("lanes.cross_h")

# 3) START — 출발선 + 사각 브래킷
st = SPEC["start"]
sx, sy = float(st["pos"][0]), float(st["pos"][1])
s_w = float(st.get("line_w", 0.02))
s_span = float(SPEC["road"]["lane_w"])                     # 차로 폭만큼 가로지른다
q = Quads()
q.rect(sx - s_w * 0.5, sy - s_span * 0.5, sx + s_w * 0.5, sy + s_span * 0.5)
q.build("MRK_Start_Line", Z_MARK, mat_white)
check_bounds("MRK_Start_Line", [(sx, sy - s_span * 0.5), (sx, sy + s_span * 0.5)])

# 브래킷 사각형: 외곽 차선(x=-2.41)을 밟지 않도록 안쪽으로 밀어 배치
MISSING.append("start.bracket (브래킷 치수) — 0.20 x 0.36, 팔길이 0.07/0.09, 폭 0.015 사용")
bx0, bx1 = sx - 0.04, sx + 0.16
by0, by1 = sy - 0.18, sy + 0.18
t, ax, ay = 0.015, 0.07, 0.09
q = Quads()
for cx0, cx1 in ((bx0, bx0 + ax), (bx1 - ax, bx1)):
    for cy0, cy1 in ((by0, by0 + t), (by1 - t, by1)):
        q.rect(cx0, cy0, cx1, cy1)                          # 가로 팔
for cx0, cx1 in ((bx0, bx0 + t), (bx1 - t, bx1)):
    for cy0, cy1 in ((by0, by0 + ay), (by1 - ay, by1)):
        q.rect(cx0, cy0, cx1, cy1)                          # 세로 팔
q.build("MRK_Start_Bracket", Z_MARK, mat_white)
check_bounds("MRK_Start_Bracket", [(bx0, by0), (bx1, by1)])

# 4) FINISH — 노랑/검정 사선 밴드
fi = SPEC["finish"]
fx = float(fi["pos"][0])
f_w = 0.10                                                   # 진행 방향 두께
if LANES.get("sub_loops"):
    # spec 의 finish.pos.y(-1.68)는 '주행선 위의 점'이라 밴드 중심으로 쓰면
    # 밴드가 y=-1.85 까지 내려가 경기장을 벗어난다. y 는 하단 회랑 폭에 맞춘다.
    # 회랑 = 외곽 노란 선과 최하단 블록 사이의 간격 (lanes.interpretation)
    y_lo = float(LANES["outer"]["min"][1])
    y_hi = float(min(lp["min"][1] for lp in LANES["sub_loops"]))
else:
    y_lo, y_hi = -1.71, -1.35
# 회랑 폭에서 차선 반폭만큼 물러난다. 밴드 평면(z=line_z)이 차선 리본을 관통하면
# 겹치는 7 mm 띠에서 렌더가 지저분해진다.
fy0 = min(y_lo, y_hi) + LANE_W * 0.5
fy1 = max(y_lo, y_hi) - LANE_W * 0.5
MISSING.append("finish.band_size — 폭 %.2f, 회랑 y=%.3f~%.3f 로 산출 (spec pos.y 는 주행선 점)"
               % (f_w, fy0, fy1))
q = Quads()
q.rect(fx - f_w * 0.5, fy0, fx + f_w * 0.5, fy1)
q.build("MRK_Finish_Band", Z_MARK, mat_stripe)
check_bounds("MRK_Finish_Band", [(fx - f_w * 0.5, fy0), (fx + f_w * 0.5, fy1)])

# 5) 헬리패드 — 검정 판 + 주황 링 + 흰 H
hp = SPEC["helipad"]
hx, hy = float(hp["pos"][0]), float(hp["pos"][1])
pw, ph = float(hp["size"][0]), float(hp["size"][1])
make_plane("MRK_Helipad_Pad", pw, ph, Z_UNDER, (hx, hy), col, mat_black)
check_bounds("MRK_Helipad_Pad", [(hx - pw * 0.5, hy - ph * 0.5), (hx + pw * 0.5, hy + ph * 0.5)])

MISSING.append("helipad.ring — 외경 0.19 / 스트로크 0.028 사용")
make_ring("MRK_Helipad_Ring", 0.19, 0.162, hx, hy, Z_OVER, mat_ring)

hl = hp.get("h_letter", {"w": 0.16, "h": 0.22, "stroke": 0.035})
lw, lh, lt = float(hl["w"]), float(hl["h"]), float(hl["stroke"])
q = Quads()
q.rect(hx - lw * 0.5, hy - lh * 0.5, hx - lw * 0.5 + lt, hy + lh * 0.5)   # 좌 기둥
q.rect(hx + lw * 0.5 - lt, hy - lh * 0.5, hx + lw * 0.5, hy + lh * 0.5)   # 우 기둥
q.rect(hx - lw * 0.5 + lt, hy - lt * 0.5, hx + lw * 0.5 - lt, hy + lt * 0.5)  # 가로대
q.build("MRK_Helipad_H", Z_OVER, mat_white)

check_sector_clearance()

bpy.context.view_layer.update()

zs = [round(ob.location.z, 5) for ob in col.objects]
bad_z = [ob.name for ob in col.objects if abs(ob.location.z - LINE_Z) > 0.0002 + 1e-9]

names = [ob.name for ob in col.objects]
n_yellow = sum(1 for n in names if n.startswith("MRK_Lane_"))
n_cross = sum(1 for n in names if n.startswith("MRK_Line_Cross"))

print("[20_markings] built %d objects | 노란 차선 %d줄 (외곽 1 + 블록 %d) "
      "| 십자 실선 %d개 (세로 %d조각 / 가로 %d조각) | z=%s"
      % (len(col.objects), n_yellow, len(LANE_RECTS) - 1, n_cross,
         len(v_segs), len(h_segs), sorted(set(zs))))
print("[20_markings] Z: 노란=%.4f 흰=%.4f (교차점 Z-파이팅 회피용 0.1mm 분리) "
      "| 십자선 style=%s" % (Z_MARK, Z_WHITE, "solid" if CROSS_SOLID else "dashed"))

# --- 검산 1) 경기장 경계 ---------------------------------------------------
lim_x, lim_y = ARENA_W * 0.5, ARENA_H * 0.5
ok1 = BOUND_MAX[0] <= lim_x + 1e-6 and BOUND_MAX[1] <= lim_y + 1e-6
print("[20_markings] 검산1 경계    : %s  max|x|=%.4f/%.2f  max|y|=%.4f/%.2f"
      % ("PASS" if ok1 else "FAIL", BOUND_MAX[0], lim_x, BOUND_MAX[1], lim_y))

# --- 검산 2) 건물 풋프린트 vs 노란 선 (블록 경계선이므로 침범 0 이 정상) ------
ok2 = not OVERRUN
print("[20_markings] 검산2 건물침범: %s  %d건%s"
      % ("PASS" if ok2 else "FAIL", len(OVERRUN),
         "" if ok2 else "  " + ", ".join("SEC%s→%s %.0fmm" % (k, n, d * 1000)
                                         for k, n, d in sorted(OVERRUN,
                                                               key=lambda t: -t[2]))))

# --- 검산 3) 흰 십자선이 블록 내부를 지나는가 -------------------------------
ok3 = not CROSS_IN_BLOCK
print("[20_markings] 검산3 십자선  : %s  블록 관통 %d건%s"
      % ("PASS" if ok3 else "FAIL", len(CROSS_IN_BLOCK),
         "" if ok3 else "  " + ", ".join("Cross%s→블록%s %.0fmm" % (a, n, v * 1000)
                                         for a, n, v in CROSS_IN_BLOCK)))

# --- 참고) 코너 반경 — 도면과 대조할 근거 (수정은 track-surveyor) ------------
print("[20_markings] 코너 반경 r / 짧은 변 대비: "
      + "  ".join("%s r=%.2f(%.0f%%)" % (n, r, ratio * 100)
                  for n, r, _s, ratio in corner_report()))

if bad_z:
    print("[20_markings] !! Z 허용범위(0.0005±0.0002) 이탈: " + ", ".join(bad_z))
if MISSING:
    print("[20_markings] 스펙 누락 필드: " + "; ".join(MISSING))
if ISSUES:
    print("[20_markings] !! 스펙 오류 의심(클램프하지 않음):\n  - " + "\n  - ".join(ISSUES))
