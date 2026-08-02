# -*- coding: utf-8 -*-
"""
10_ground.py — 경기장 바닥면 (track-builder)

생성물
    GND_Base    5.0 x 3.5 주행면. **포트홀 위치에 실제 구멍이 뚫린 평면**
    GND_Under   주행면 12 mm 아래의 받침 슬래브 (구멍 너머로 허공이 보이지 않게)
    GND_Frame   트레이 테두리. 주행면 '바깥'으로 세운다 (SPEC.arena.frame.placement)
    MAT_Asphalt 노이즈 2단(매크로 얼룩 + 미세 그레인) 아스팔트
    MAT_Frame   테두리/받침 공용 짙은 회색

왜 베이스에 구멍을 뚫는가
    30_hazards 의 포트홀은 make_disc(center_z<0) 로 노면 아래로 파인 형상이다.
    베이스가 z=0 에서 끊김 없이 이어져 있으면 위에서 내려오는 시선이 베이스에 먼저
    닿아 파인 부분이 **영원히 가려진다**. 그러면 "오목하게 만들었는데 스티커처럼 보인다"
    는 결과가 나온다. 그래서 SPEC["potholes"] 를 읽어 베이스 자체에 구멍을 낸다.
    구멍 반경 = 포트홀 반경 r (30_hazards 가 r*1.02~1.12 로 덮어 이음매를 가린다).

좌표는 전부 SPEC(= spec/track_spec.json) 에서만 가져온다. 여기서 추정하지 않는다.
"""

import bpy
import math
import os

WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
exec(open(os.path.join(WORKSPACE, "scripts", "00_common.py")).read())

# ---------------------------------------------------------------- 튜닝 상수
# 스펙에 없는 값만 여기 둔다. 스펙에 있는 값은 절대 여기 복사하지 않는다.
HOLE_PAD = 0.06        # 포트홀 원 구멍을 감싸는 사각 컷의 여유 (칼라 폭)
COLLAR_SEG = 48        # 사각 컷 ↔ 원 구멍 사이 칼라 분할 (8의 배수여야 모서리가 맞는다)
UNDER_TOP_Z = -0.012   # 받침 슬래브 윗면 (주행면과 겹치면 전면 Z-파이팅)
UNDER_H = 0.020        # 받침 슬래브 두께
FRAME_COLOR = (0.085, 0.085, 0.095)   # 스펙 누락 — 트레이 테두리 색
FRAME_ROUGH = 0.46

MISSING = []           # 스펙 누락 필드 (마지막에 보고. 멈추지 않는다)
ISSUES = []            # 스펙 오류 의심 (클램프하지 않고 보고만)


# ---------------------------------------------------------------- 머티리얼
def reset_material_nodes(name):
    """머티리얼 노드 트리를 비우고 Principled+Output 만 남긴다.

    스크립트를 재실행할 때 노드를 지우지 않으면 노이즈 노드가 계속 쌓여
    링크가 뒤엉킨다. purge() 는 오브젝트만 지우므로 머티리얼은 여기서 초기화한다.
    """
    mat = get_or_create_material(name)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (760, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (440, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat, nt, bsdf


def build_asphalt_material():
    """균일한 회색을 금지한다.

    노면은 이 씬에서 가장 넓은 면적을 차지한다. 단색 회색이면 렌더 첫 프레임부터
    CG 로 읽힌다. 스케일이 다른 노이즈 2장을 섞어 (1) 넓은 보수 자국 얼룩,
    (2) 미세 골재 입자를 만들고, 같은 필드로 러프니스와 범프까지 흔든다.
    """
    mat, nt, bsdf = reset_material_nodes("MAT_Asphalt")

    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-1180, 0)

    # 매크로 — 수십 cm 단위 얼룩 (아스팔트 보수 자국)
    n_mac = nt.nodes.new("ShaderNodeTexNoise")
    n_mac.location = (-960, 220)
    _set_input(n_mac, "Scale", 9.0)
    _set_input(n_mac, "Detail", 3.0)
    _set_input(n_mac, "Roughness", 0.55)

    # 그레인 — mm 단위 골재 입자
    n_gr = nt.nodes.new("ShaderNodeTexNoise")
    n_gr.location = (-960, -220)
    _set_input(n_gr, "Scale", 210.0)
    _set_input(n_gr, "Detail", 6.0)
    _set_input(n_gr, "Roughness", 0.62)

    nt.links.new(tc.outputs["Object"], n_mac.inputs["Vector"])
    nt.links.new(tc.outputs["Object"], n_gr.inputs["Vector"])

    # Mix 노드는 3.x/4.x 사이에서 소켓 이름이 갈린다. Math 노드로 섞으면 버전 안전.
    m_a = nt.nodes.new("ShaderNodeMath")
    m_a.location = (-720, 220)
    m_a.operation = 'MULTIPLY'
    m_a.inputs[1].default_value = 0.62
    nt.links.new(n_mac.outputs["Fac"], m_a.inputs[0])

    m_b = nt.nodes.new("ShaderNodeMath")
    m_b.location = (-720, -220)
    m_b.operation = 'MULTIPLY'
    m_b.inputs[1].default_value = 0.38
    nt.links.new(n_gr.outputs["Fac"], m_b.inputs[0])

    m_sum = nt.nodes.new("ShaderNodeMath")
    m_sum.location = (-520, 0)
    m_sum.operation = 'ADD'
    nt.links.new(m_a.outputs["Value"], m_sum.inputs[0])
    nt.links.new(m_b.outputs["Value"], m_sum.inputs[1])

    # 베이스 컬러 램프 — 어두운 아스팔트 안에서만 대비를 준다.
    # "밋밋하다" 피드백이 오면 베이스 컬러를 밝히기 전에 이 3점의 간격부터 벌린다.
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-300, 120)
    cr = ramp.color_ramp
    cr.elements[0].position = 0.0
    cr.elements[0].color = (0.028, 0.028, 0.031, 1.0)
    cr.elements[1].position = 1.0
    cr.elements[1].color = (0.108, 0.108, 0.112, 1.0)
    mid = cr.elements.new(0.46)
    mid.color = (0.058, 0.058, 0.063, 1.0)
    nt.links.new(m_sum.outputs["Value"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

    # 러프니스 편차 — 물기 마른 자국처럼 넓게 흔든다
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.location = (-300, -200)
    _set_input(mr, "From Min", 0.25)
    _set_input(mr, "From Max", 0.75)
    _set_input(mr, "To Min", 0.70)
    _set_input(mr, "To Max", 0.94)
    nt.links.new(n_mac.outputs["Fac"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], bsdf.inputs["Roughness"])

    # 범프 — 실제 지오메트리 없이 골재 요철
    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (140, -260)
    _set_input(bump, "Strength", 0.28)
    _set_input(bump, "Distance", 0.0025)
    nt.links.new(m_sum.outputs["Value"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    _set_input(bsdf, "Metallic", 0.0)
    _set_input(bsdf, "Specular IOR Level", 0.32)   # 4.x
    _set_input(bsdf, "Specular", 0.32)             # 3.x
    mat.diffuse_color = rgba(SPEC["colors"]["asphalt"])
    return mat


# ---------------------------------------------------------------- 베이스 메시
def hole_squares():
    """포트홀마다 [사각 컷 정보] 를 만든다. 좌표는 SPEC 에서만 읽는다."""
    out = []
    for ph in SPEC.get("potholes", []):
        cx, cy = float(ph["pos"][0]), float(ph["pos"][1])
        r = float(ph.get("r", 0.10))
        out.append({"id": ph.get("id"), "c": (cx, cy), "r": r, "half": r + HOLE_PAD})
    return out


def band_rects(x0, y0, x1, y1, squares):
    """사각 구멍을 피해 평면을 직사각형들로 분할 (수평 밴드 스윕).

    구멍 주변만 잘라내므로 결과는 10여 개 사각형이다. 밴드 경계에서 T-정점이
    생기지만 전부 z=0 동일 평면이라 렌더에 균열이 생기지 않는다.
    """
    cuts = {y0, y1}
    for s in squares:
        cuts.add(s["c"][1] - s["half"])
        cuts.add(s["c"][1] + s["half"])
    ys = sorted(v for v in cuts if y0 - 1e-9 <= v <= y1 + 1e-9)

    rects = []
    for i in range(len(ys) - 1):
        by0, by1 = ys[i], ys[i + 1]
        if by1 - by0 < 1e-6:
            continue
        ymid = 0.5 * (by0 + by1)
        spans = sorted(
            (s["c"][0] - s["half"], s["c"][0] + s["half"])
            for s in squares
            if (s["c"][1] - s["half"]) < ymid < (s["c"][1] + s["half"])
        )
        cur = x0
        for sx0, sx1 in spans:
            if sx0 > cur + 1e-6:
                rects.append((cur, by0, sx0, by1))
            cur = max(cur, sx1)
        if cur < x1 - 1e-6:
            rects.append((cur, by0, x1, by1))
    return rects


def build_base():
    hw, hh = ARENA_W * 0.5, ARENA_H * 0.5
    squares = hole_squares()

    # 구멍이 경기장을 벗어나거나 서로 겹치면 클램프하지 않고 보고한다.
    for i, s in enumerate(squares):
        cx, cy, h = s["c"][0], s["c"][1], s["half"]
        if abs(cx) + h > hw or abs(cy) + h > hh:
            ISSUES.append("pothole#%s 사각 컷이 경기장을 벗어남 c=(%.3f,%.3f) half=%.3f"
                          % (s["id"], cx, cy, h))
        for t in squares[i + 1:]:
            if (abs(cx - t["c"][0]) < h + t["half"] and
                    abs(cy - t["c"][1]) < h + t["half"]):
                ISSUES.append("pothole#%s 와 #%s 의 사각 컷이 겹침" % (s["id"], t["id"]))

    verts = []
    index = {}

    def vid(x, y):
        key = (round(x, 6), round(y, 6))
        if key not in index:
            index[key] = len(verts)
            verts.append((x, y, 0.0))
        return index[key]

    faces = []
    for rx0, ry0, rx1, ry1 in band_rects(-hw, -hh, hw, hh, squares):
        faces.append((vid(rx0, ry0), vid(rx1, ry0), vid(rx1, ry1), vid(rx0, ry1)))

    # 사각 컷 ↔ 원 구멍 사이의 칼라(annulus). 각도 파라미터로 사각 경계를 훑는다.
    for s in squares:
        cx, cy = s["c"]
        r, h = s["r"], s["half"]
        outer, inner = [], []
        for k in range(COLLAR_SEG):
            a = 2.0 * math.pi * k / COLLAR_SEG
            ca, sa = math.cos(a), math.sin(a)
            t = h / max(abs(ca), abs(sa))       # 사각 경계까지의 거리
            outer.append(vid(cx + t * ca, cy + t * sa))
            inner.append(vid(cx + r * ca, cy + r * sa))
        for k in range(COLLAR_SEG):
            j = (k + 1) % COLLAR_SEG
            faces.append((outer[k], outer[j], inner[j], inner[k]))

    base = mesh_object("GND_Base", verts, faces, (0, 0, 0), "00_Ground", "MAT_Asphalt")
    return base, squares


def build_frame():
    """주행면 '바깥'으로 세우는 테두리 링.

    안쪽으로 세우면 폭 0.06 프레임이 y=-1.69 까지 들어와 하단 주행선(y=-1.68)에서
    차체가 닿는다. SPEC.arena.frame.placement 가 'outward' 인 이유.
    """
    fr = SPEC["arena"].get("frame")
    if fr is None:
        MISSING.append("arena.frame (기본값 w=arena.border, h=0.04, 바깥쪽 사용)")
        fr = {"w": SPEC["arena"].get("border", 0.06), "h": 0.04, "placement": "outward"}
    fw = float(fr.get("w", 0.06))
    fh = float(fr.get("h", 0.04))
    if fr.get("placement", "outward") != "outward":
        ISSUES.append("arena.frame.placement=%r — 안쪽 배치는 하단 주행선을 침범한다"
                      % fr.get("placement"))

    a, b = ARENA_W * 0.5, ARENA_H * 0.5          # 주행면 = 프레임 안쪽 면
    A, B = a + fw, b + fw                        # 프레임 바깥 면
    z0, z1 = UNDER_TOP_Z, fh

    inner = [(-a, -b), (a, -b), (a, b), (-a, b)]
    outer = [(-A, -B), (A, -B), (A, B), (-A, B)]
    verts = ([(x, y, z0) for x, y in inner] + [(x, y, z0) for x, y in outer] +
             [(x, y, z1) for x, y in inner] + [(x, y, z1) for x, y in outer])
    IB, OB, IT, OT = 0, 4, 8, 12

    faces = []
    for i in range(4):
        j = (i + 1) % 4
        faces.append((IB + i, IB + j, OB + j, OB + i))   # 바닥 링 (-Z)
        faces.append((IT + i, OT + i, OT + j, IT + j))   # 윗면 링 (+Z)
        faces.append((OB + i, OB + j, OT + j, OT + i))   # 바깥 벽
        faces.append((IB + i, IT + i, IT + j, IB + j))   # 안쪽 벽
    frame = mesh_object("GND_Frame", verts, faces, (0, 0, 0), "00_Ground", "MAT_Frame")
    add_bevel(frame, width=0.0012, segments=2)
    return frame, (A, B, fh)


def build_under(A, B):
    """구멍 너머로 허공이 보이지 않게 받는 슬래브. 주행면과 12 mm 띄운다."""
    return make_box("GND_Under", (A * 2.0, B * 2.0, UNDER_H),
                    (0.0, 0.0, UNDER_TOP_Z - UNDER_H), "00_Ground", "MAT_Frame")


# ---------------------------------------------------------------- 실행
purge("GND_")
col = link_collection("00_Ground")

build_asphalt_material()
get_or_create_material("MAT_Frame", color=FRAME_COLOR, roughness=FRAME_ROUGH, metallic=0.12)

base, squares = build_base()
frame, (FX, FY, FH) = build_frame()
under = build_under(FX, FY)

bpy.context.view_layer.update()

print("[10_ground] built %d objects | base=%.3f x %.3f m | frame outer=%.2f x %.2f h=%.3f "
      "| pothole cutouts=%d | faces=%d"
      % (len(col.objects), base.dimensions.x, base.dimensions.y,
         FX * 2.0, FY * 2.0, FH, len(squares), len(base.data.polygons)))
if MISSING:
    print("[10_ground] 스펙 누락 필드: " + "; ".join(MISSING))
if ISSUES:
    print("[10_ground] !! 스펙 오류 의심(클램프하지 않음): " + "; ".join(ISSUES))
