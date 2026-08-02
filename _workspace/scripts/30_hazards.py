# -*- coding: utf-8 -*-
"""
30_hazards.py — 위험 요소 (track-builder)

생성물 (전부 02_Hazards / HZD_ 접두사)
    HZD_Pothole_01/02   실제로 파인 포트홀. make_disc(center_z<0) + 불규칙 림
    HZD_Barrier_01/02   노랑/검정 사선 턱 (0.26 x 0.03 x 0.025)
    HZD_Crack_01..NN    노면 균열 데칼 (지오메트리 아님 — 알파 텍스처 평면)

포트홀이 '스티커'가 되지 않으려면
    검은 원판을 노면에 얹으면 그림자가 생기지 않아 즉시 스티커로 보인다. 여기서는
    중심 정점을 SPEC.potholes[].depth (8 mm) 만큼 내려 실제로 오목하게 만든다.
    단, 10_ground 가 베이스에 반경 r 의 구멍을 뚫어 두지 않으면 노면이 위를 덮어
    파인 부분이 보이지 않는다. 두 스크립트는 이 지점에서 한 쌍이다.
      - 베이스 구멍 반경 : r
      - 포트홀 림 반경   : r * (1.02 ~ 1.12)  ← 항상 구멍보다 커서 이음매를 덮는다
      - 림 높이          : +0.4 mm            ← 베이스와 겹치는 띠에서 Z-파이팅 방지

균열은 왜 지오메트리가 아닌가
    도면 곳곳의 검은 무늬를 폴리곤으로 깎으면 정점만 수만 개 늘고 카메라 거리에서
    보이는 차이는 없다. 알파 데칼 평면 한 장이 같은 인상을 만든다.
"""

import bpy
import math
import os

WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
exec(open(os.path.join(WORKSPACE, "scripts", "00_common.py")).read())

# ---------------------------------------------------------------- 튜닝 상수
POTHOLE_SEG = 32
RIM_LIFT = 0.0004          # 포트홀 림을 노면 위로 살짝 (베이스와 겹치는 띠의 Z-파이팅 방지)
RIM_JITTER = (1.02, 1.12)  # 림 반경 배율 범위 — 하한이 1.0 초과여야 구멍을 확실히 덮는다
RIM_Z_WOBBLE = 0.0002      # 림 높이 요철
CRACK_Z = 0.0003           # 균열 데칼 (마킹 0.0005 보다 아래, 노면 위)
STRIPE_SCALE = 16.0        # 사선 간격 ≈ 0.3/scale m

# 스펙 누락: 균열 데칼 좌표는 track_spec.json 에 없다 (도면의 검은 무늬는 좌표화되지 않음).
# 주행 회랑 위주로 배치하되 포트홀/헬리패드/건물 풋프린트를 피한다. (x, y, w, h, deg)
CRACK_PATCHES = [
    (-0.55, -0.72, 0.75, 0.55, 14.0),
    (0.56, 0.82, 0.55, 0.50, -10.0),
    (2.22, 0.10, 0.46, 0.80, 4.0),
    (-2.16, -1.16, 0.50, 0.46, 22.0),
    (0.10, 1.46, 0.70, 0.38, -8.0),
    (1.36, -0.74, 0.60, 0.50, 34.0),
    (-1.12, -0.98, 0.58, 0.46, -28.0),
]

MISSING = ["crack_decals (균열 데칼 좌표) — 스크립트 상단 CRACK_PATCHES 로 대체"]
ISSUES = []

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


def build_stripe_material(name="MAT_HazardStripe", scale=STRIPE_SCALE):
    """20_markings 의 FINISH 밴드와 같은 머티리얼. 두 스크립트가 각자 정의를 갖고 있어
    실행 순서와 무관하게 자기 완결적으로 돈다 (같은 이름 → 같은 데이터블록 재사용)."""
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
    cr.interpolation = 'CONSTANT'
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


def build_crack_material(name="MAT_Crack"):
    """알파 데칼 균열.

    Voronoi 의 '셀 경계까지 거리' 를 얇은 임계로 자르면 그물 모양 균열이 나온다.
    좌표는 오브젝트가 아니라 **월드 위치**를 쓴다 — 그래야 데칼 7장이 각자 다른
    무늬를 갖고, 서로 이어 붙여도 패턴이 반복되지 않는다.
    """
    mat, nt, bsdf = reset_material_nodes(name)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    geo.location = (-940, 0)

    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.location = (-740, 160)
    try:
        vor.feature = 'DISTANCE_TO_EDGE'
    except Exception:
        ISSUES.append("Voronoi DISTANCE_TO_EDGE 미지원 — 균열이 셀 무늬로 보일 수 있음")
    _set_input(vor, "Scale", 26.0)
    _set_input(vor, "Randomness", 1.0)
    nt.links.new(geo.outputs["Position"], vor.inputs["Vector"])

    crack = nt.nodes.new("ShaderNodeValToRGB")
    crack.location = (-520, 160)
    cc = crack.color_ramp
    cc.interpolation = 'LINEAR'
    cc.elements[0].position = 0.0
    cc.elements[0].color = (1, 1, 1, 1)
    cc.elements[1].position = 0.05          # 얇을수록 균열, 굵으면 갈라진 논바닥
    cc.elements[1].color = (0, 0, 0, 1)
    nt.links.new(vor.outputs["Distance"], crack.inputs["Fac"])

    # 마스크 — 균열이 판 전체를 덮으면 가짜다. 넓은 노이즈로 군데군데만 남긴다.
    mask_n = nt.nodes.new("ShaderNodeTexNoise")
    mask_n.location = (-740, -200)
    _set_input(mask_n, "Scale", 2.4)
    _set_input(mask_n, "Detail", 2.0)
    nt.links.new(geo.outputs["Position"], mask_n.inputs["Vector"])

    mask_r = nt.nodes.new("ShaderNodeValToRGB")
    mask_r.location = (-520, -200)
    mc = mask_r.color_ramp
    mc.elements[0].position = 0.42
    mc.elements[0].color = (0, 0, 0, 1)
    mc.elements[1].position = 0.62
    mc.elements[1].color = (1, 1, 1, 1)
    nt.links.new(mask_n.outputs["Fac"], mask_r.inputs["Fac"])

    mul = nt.nodes.new("ShaderNodeMath")
    mul.location = (-280, 0)
    mul.operation = 'MULTIPLY'
    nt.links.new(crack.outputs["Color"], mul.inputs[0])
    nt.links.new(mask_r.outputs["Color"], mul.inputs[1])
    nt.links.new(mul.outputs["Value"], bsdf.inputs["Alpha"])

    _set_input(bsdf, "Base Color", (0.012, 0.012, 0.014, 1.0))
    _set_input(bsdf, "Roughness", 0.92)
    _set_input(bsdf, "Metallic", 0.0)

    for attr, val in (("blend_method", 'BLEND'),        # EEVEE Legacy
                      ("shadow_method", 'NONE'),
                      ("surface_render_method", 'BLENDED')):   # EEVEE Next (4.2+)
        try:
            setattr(mat, attr, val)
        except Exception:
            pass
    mat.diffuse_color = (0.02, 0.02, 0.02, 1.0)
    return mat


# ---------------------------------------------------------------- 포트홀
def build_pothole(ph, mat):
    pid = int(ph.get("id", 0))
    cx, cy = float(ph["pos"][0]), float(ph["pos"][1])
    r = float(ph.get("r", 0.10))
    depth = float(ph.get("depth", 0.008))
    if "depth" not in ph:
        MISSING.append("potholes[%d].depth — 0.008 사용" % pid)

    name = "HZD_Pothole_%02d" % pid
    ob = make_disc(name, r, (cx, cy, RIM_LIFT), POTHOLE_SEG,
                   center_z=-(depth + RIM_LIFT), col="02_Hazards", mat=mat)

    # 림을 불규칙하게 — 완벽한 원은 파손이 아니라 배수구로 보인다.
    # 결정적(사인 합성)이라 재실행해도 같은 형상이 나온다.
    lo, hi = RIM_JITTER
    mid, amp = 0.5 * (lo + hi), 0.5 * (hi - lo)
    phase = 1.7 * pid
    me = ob.data
    for i, v in enumerate(me.vertices):
        if i == 0:
            continue                      # 0 번은 바닥 중심 정점
        a = 2.0 * math.pi * (i - 1) / POTHOLE_SEG
        f = mid + amp * (0.64 * math.sin(3.0 * a + phase) +
                         0.36 * math.sin(7.0 * a + 2.1 * phase))
        rr = r * f
        v.co = (rr * math.cos(a), rr * math.sin(a),
                RIM_Z_WOBBLE * math.sin(5.0 * a + phase))
    me.update()
    return ob


# ---------------------------------------------------------------- 배리어
def build_barrier(bar, mat):
    bid = int(bar.get("id", 0))
    bx, by = float(bar["pos"][0]), float(bar["pos"][1])
    size = bar.get("size")
    if size is None:
        MISSING.append("barriers[%d].size — 0.26 x 0.03 x 0.025 사용" % bid)
        size = [0.26, 0.03, 0.025]
    ob = make_box("HZD_Barrier_%02d" % bid, size, (bx, by, 0.0), "02_Hazards", mat)
    ob.rotation_euler = (0.0, 0.0, float(bar.get("yaw", 0.0)))
    add_bevel(ob, width=0.0012, segments=2)

    # 회전 후 실제 점유 범위가 경기장 안인지 — 벗어나면 클램프하지 않고 보고
    yaw = float(bar.get("yaw", 0.0))
    hx = abs(size[0] * 0.5 * math.cos(yaw)) + abs(size[1] * 0.5 * math.sin(yaw))
    hy = abs(size[0] * 0.5 * math.sin(yaw)) + abs(size[1] * 0.5 * math.cos(yaw))
    if abs(bx) + hx > ARENA_W * 0.5 or abs(by) + hy > ARENA_H * 0.5:
        ISSUES.append("barrier#%d 가 경기장을 벗어남 pos=(%.3f,%.3f)" % (bid, bx, by))
    return ob


# ---------------------------------------------------------------- 균열 데칼
def build_cracks(mat):
    made = []
    holes = [(float(p["pos"][0]), float(p["pos"][1]), float(p.get("r", 0.1)))
             for p in SPEC.get("potholes", [])]
    for i, (x, y, w, h, deg) in enumerate(CRACK_PATCHES, start=1):
        rot = math.radians(deg)
        # 회전 포함 AABB 반폭 — 경계/포트홀 침범 검사용
        ex = abs(w * 0.5 * math.cos(rot)) + abs(h * 0.5 * math.sin(rot))
        ey = abs(w * 0.5 * math.sin(rot)) + abs(h * 0.5 * math.cos(rot))
        if abs(x) + ex > ARENA_W * 0.5 or abs(y) + ey > ARENA_H * 0.5:
            ISSUES.append("HZD_Crack_%02d 가 경기장을 벗어남 (%.2f, %.2f)" % (i, x, y))
        for hx, hy, hr in holes:
            if abs(x - hx) < ex + hr and abs(y - hy) < ey + hr:
                ISSUES.append("HZD_Crack_%02d 이 포트홀 구멍을 덮는다 — 파인 형상이 가려짐"
                              % i)
        ob = make_plane("HZD_Crack_%02d" % i, w, h, CRACK_Z, (x, y), "02_Hazards", mat)
        ob.rotation_euler = (0.0, 0.0, rot)
        made.append(ob)
    return made


# ---------------------------------------------------------------- 실행
purge("HZD_")
col = link_collection("02_Hazards")

mat_hole = get_or_create_material("MAT_PotholeDark", color=(0.016, 0.016, 0.018),
                                  roughness=0.95, metallic=0.0)
mat_stripe = build_stripe_material()
mat_crack = build_crack_material()

potholes = [build_pothole(ph, mat_hole) for ph in SPEC.get("potholes", [])]
barriers = [build_barrier(b, mat_stripe) for b in SPEC.get("barriers", [])]
cracks = build_cracks(mat_crack)

if len(potholes) != 2:
    ISSUES.append("포트홀이 %d 개 — 명세 고정 수량은 2" % len(potholes))
if len(barriers) != 2:
    ISSUES.append("배리어가 %d 개 — 명세 고정 수량은 2" % len(barriers))

bpy.context.view_layer.update()

print("[30_hazards] built %d objects | potholes=%d (depth %s m) barriers=%d cracks=%d "
      "| crack_z=%.4f rim_lift=%.4f"
      % (len(col.objects), len(potholes),
         [round(float(p.get("depth", 0.008)), 4) for p in SPEC.get("potholes", [])],
         len(barriers), len(cracks), CRACK_Z, RIM_LIFT))
if MISSING:
    print("[30_hazards] 스펙 누락 필드: " + "; ".join(MISSING))
if ISSUES:
    print("[30_hazards] !! 스펙 오류 의심(클램프하지 않음): " + "; ".join(ISSUES))
