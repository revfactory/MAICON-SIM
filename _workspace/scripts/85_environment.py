# -*- coding: utf-8 -*-
"""
85_environment.py — 실내 경기장 환경 (cinematographer 산출)

실행 순서:  ... → 80_motion → **85_environment** → 90_camera → 95_render

왜 필요한가
------------------------------------------------------------------------
지금까지의 렌더는 경기장 밖이 검은 허공이었다. 5 m 디오라마가 우주에 떠 있는
것처럼 보이는 가장 큰 원인이고, 카메라를 아무리 낮춰도 이건 해결되지 않는다.
바닥·벽·천장이 프레임 안에 들어와야 "실내에 놓인 경기장"으로 읽힌다.

무엇을 만드나
------------------------------------------------------------------------
  ENV_Floor           콘크리트 바닥 12 x 12 m,  Z = -0.034 (트레이 바닥과 동일면)
  ENV_Wall_N/S/E/W    밝은 회색 벽 4면, 안쪽 면이 원점에서 ±5.5 m, 높이 3.0 m
  ENV_Skirt_N/S/E/W   걸레받이 (폭 0.10 m 짙은 회색) — 실내감의 절반은 이것이다
  ENV_Ceiling         천장 슬래브, 아랫면 Z = 3.0 m
  ENV_CeilPanel_01..06  천장 이미시브 패널 (3 x 2)
  ENV_CeilLamp_01..06   패널과 짝을 이루는 약한 AREA 라이트 (CEIL_LAMP_ENABLE 로 끈다)

전부 컬렉션 `09_Environment` 에 들어간다.

치수 근거 (씬 실측값 — 추정 아님)
------------------------------------------------------------------------
  씬 범위        X -2.560~2.560 / Y -1.810~1.810 / Z -0.032~0.643
  카메라 최대 수평반경 3.762 m,  카메라 높이 0.065~0.950 m
  → 벽 안쪽 면 ±5.5 m  (카메라와 1.738 m 여유)
  → 천장 아랫면 3.0 m  (카메라와 2.050 m 여유)
벽을 이보다 좁히면 오비탈 컷에서 카메라가 벽을 뚫는다.

조명과의 상호작용 — 이 스크립트에서 가장 중요한 부분
------------------------------------------------------------------------
1) 모든 ENV_ 오브젝트는 **그림자를 드리우지 않는다** (visible_shadow = False).
   LGT_Rim_A/B 는 고도 10°/15° 의 SUN 이다. 벽이 그림자를 드리우면 이 두 림
   라이트가 벽에 완전히 막혀 스카이라인이 사라진다. 그림자를 끄면 빛은 벽을
   통과해 건물 윤곽을 그대로 만들고, 벽 자신은 여전히 빛을 받아 밝게 보인다.
   그림자를 '받는' 것은 영향받지 않으므로 바닥에는 트레이 그림자가 그대로 진다.

2) EEVEE Next 의 GI 는 스크린 스페이스다 (95_render.py: ray_tracing_method='SCREEN',
   fast_gi_method='AMBIENT_OCCLUSION_ONLY'). 즉 **화면에 보이는 벽만** 바운스를
   준다. 화면 밖 벽은 색을 돌려주지 않는다. 기대만큼 바운스가 붙지 않는 이유이고,
   천장 패널에 실제 AREA 라이트를 짝지어 둔 이유이기도 하다.

3) 이 스크립트는 **기존 LGT_* 를 절대 건드리지 않는다.** 실행 순서가 85 → 90 이라
   여기서 고쳐도 90 이 덮어쓴다. 대신 아래 LIGHT_ADJUST 에 제안치만 담아 print 한다.
   테스트 렌더를 보고 판단해 90_camera.py 상단 상수에 반영할 것.
"""

import bpy
import math
import os

WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
exec(open(os.path.join(WORKSPACE, "scripts", "00_common.py")).read())


# ==========================================================================
# 0. 90_camera.py 에 반영할 조명 제안치 (여기서 적용하지 않는다 — 제안만 한다)
# ==========================================================================
# 근거: (a) 검은 배경이 밝은 회색 벽으로 바뀌면 프레임 평균 휘도가 올라가고,
#          AgX 의 하이라이트 롤오프 때문에 경기장이 상대적으로 어둡게 읽힌다.
#       (b) 화면에 들어온 벽이 스크린 스페이스 GI 로 키/필을 되돌려준다.
#       (c) 배경이 밝아진 만큼 림 라이트를 같이 올리지 않으면 건물 윤곽이 배경에
#          묻힌다 — 스카이라인은 밝기 자체가 아니라 배경과의 '차이'로 보인다.
#       (d) 월드는 이제 방에 갇혀 거의 보이지 않는다. 앰비언트가 이중으로 걸리는
#          것을 막기 위해 강도를 낮춘다.
LIGHT_ADJUST = {
    "KEY_POWER":      {"from": 520.0, "to": 430.0,
                       "why": "벽 바운스가 더해진다. 유지하면 노면 하이라이트가 뜬다"},
    "FILL_POWER":     {"from": 170.0, "to": 115.0,
                       "why": "밝은 벽(알베도 0.58~0.74)이 필 역할을 나눠 갖는다"},
    "RIM_A_energy":   {"from": 2.9,   "to": 3.3,
                       "why": "배경이 밝아졌다. 같이 올려야 스카이라인 분리가 유지된다"},
    "RIM_B_energy":   {"from": 1.8,   "to": 2.1,
                       "why": "동일. 반대쪽 윤곽선용"},
    "WORLD_STRENGTH": {"from": 1.0,   "to": 0.60,
                       "why": "실내라 월드는 거의 가려진다. 앰비언트 이중 계상 방지"},
}
# 위 제안은 CEIL_LAMP_ENABLE = True 기준이다. 램프를 끄면 KEY/FILL 은 원래 값을 유지하고
# WORLD_STRENGTH 만 0.8 정도로 낮추는 편이 맞다.
LIGHT_ADJUST_NOTE_BRIGHT = (
    "과노출이면 → WALL_ALBEDO_HI 0.74→0.66, PANEL_EMISSION 3.0→2.0, "
    "CEIL_LAMP_POWER 16→8 순으로 내린다. view_settings.exposure 는 마지막 수단."
)
LIGHT_ADJUST_NOTE_DARK = (
    "여전히 어두우면 → CEIL_LAMP_POWER 16→26, 그다음 90 의 KEY_POWER 를 올린다. "
    "벽 알베도를 0.8 이상으로 올리는 것은 금물(반사가 실제 계산되어 바로 뜬다)."
)


# ==========================================================================
# 1. 치수 상수  — 전부 미터. 씬 실측값에서 유도했다
# ==========================================================================
TRAY_BOTTOM_Z = -0.032       # 씬 실측: 트레이 바닥
FLOOR_EPS     = 0.002        # 트레이 바닥과 완전 동일면이면 Z-파이팅. 2 mm 만 내린다
FLOOR_Z       = TRAY_BOTTOM_Z - FLOOR_EPS      # -0.034
FLOOR_SIZE    = 12.0         # 12 x 12 m — 벽 바깥까지 덮어 벽 밑에 틈이 없다

ROOM_HALF     = 5.5          # 벽 '안쪽 면' 까지의 거리 (내부 11.0 x 11.0 m)
WALL_T        = 0.12         # 벽 두께 (얇은 판이면 모서리에서 종이처럼 보인다)
WALL_TOP      = 3.0          # 천장 아랫면 = 벽 유효 높이
WALL_OVER     = 0.06         # 천장 슬래브 안으로 밀어 넣는 여유 (이음매 방지)

SKIRT_H       = 0.10         # 걸레받이 높이
SKIRT_T       = 0.022        # 실내로 튀어나오는 두께
SKIRT_EMBED   = 0.004        # 벽 안으로 파묻는 깊이 (동일면 Z-파이팅 회피)

CEIL_Z        = 3.0          # 천장 아랫면
CEIL_T        = 0.12         # 천장 슬래브 두께

# 천장 패널 — 3(X) x 2(Y)
PANEL_SX, PANEL_SY, PANEL_H = 2.40, 0.55, 0.05
PANEL_XS = (-3.30, 0.00, 3.30)
PANEL_YS = (-2.40, 2.40)
PANEL_TOP_Z = CEIL_Z                      # 패널 윗면이 천장에 붙는다
PANEL_BOT_Z = CEIL_Z - PANEL_H            # 2.95

# 패널과 짝을 이루는 실제 광원.
# 이미시브 지오메트리는 EEVEE 에서 화면에 보일 때만 GI 로 씬을 밝힌다.
# 천장은 대부분의 컷에서 화면 밖이므로, 광원 없이는 '보이기만 하고 비추지 않는다'.
CEIL_LAMP_ENABLE = True
CEIL_LAMP_POWER  = 16.0                   # 6개 합 96 W — 키(520 W) 대비 약 10 % 앰비언트
CEIL_LAMP_COLOR  = (0.97, 0.98, 1.0)      # 형광/LED 다운라이트에 가까운 중성백색

# 머티리얼 밝기 — 벽 알베도가 0.8 을 넘으면 EEVEE Next 의 레이트레이싱이
# 실제로 반사를 계산해 프레임 전체가 뜬다. 0.6~0.75 를 지킨다.
CONCRETE_LO, CONCRETE_MID, CONCRETE_HI = 0.135, 0.205, 0.285
WALL_ALBEDO_LO, WALL_ALBEDO_HI = 0.58, 0.74
SKIRT_COLOR   = (0.085, 0.088, 0.095)
CEIL_COLOR    = (0.50, 0.51, 0.52)
PANEL_COLOR   = (0.96, 0.975, 1.0)
PANEL_EMISSION = 3.0

# 카메라 여유 검증용 실측값 (90_camera.py 가 만드는 리그의 실제 범위)
CAM_MAX_R = 3.762
CAM_MAX_Z = 0.950

COL_NAME = "09_Environment"
WARN = []


# ==========================================================================
# 2. 헬퍼
# ==========================================================================
def env_reset_material(name):
    """머티리얼 노드 트리를 비우고 Principled + Output 만 남긴다.

    purge() 는 오브젝트만 지운다. 노드를 지우지 않고 재실행하면 노이즈 노드가
    계속 쌓여 링크가 뒤엉키고, 두 번째 실행부터 룩이 조용히 달라진다.
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


def no_shadow(obj):
    """이 오브젝트를 그림자 캐스터에서 뺀다 (받는 것은 그대로).

    벽이 그림자를 드리우면 고도 10~15° 의 SUN 림 라이트가 통째로 막힌다.
    데모의 스카이라인이 죽는 가장 흔한 원인이므로 모든 ENV_ 에 적용한다.
    """
    if hasattr(obj, "visible_shadow"):      # 4.2+ / 5.x 오브젝트 레이 가시성
        obj.visible_shadow = False
    # EEVEE Legacy(4.1 이하) 는 오브젝트 단위 레이 가시성이 없다 — 머티리얼로 끈다
    if obj.data is not None and getattr(obj.data, "materials", None):
        for m in obj.data.materials:
            if m is not None and hasattr(m, "shadow_method"):
                try:
                    m.shadow_method = 'NONE'
                except (TypeError, ValueError):
                    pass
    return obj


def env_box(name, size, loc, mat):
    ob = make_box(name, size, loc, col=COL_NAME, mat=mat)
    return no_shadow(ob)


# ==========================================================================
# 3. 멱등성 — 오브젝트 + 고아 라이트 데이터 정리
# ==========================================================================
n_purged = purge("ENV_")
for _ld in [l for l in bpy.data.lights if l.users == 0]:
    bpy.data.lights.remove(_ld)

col = link_collection(COL_NAME)

# 런타임 편의: scene-inspector 가 컬렉션/접두사 표를 훑을 때 09 가 빠지지 않도록
if COL_NAME not in COLLECTIONS:
    COLLECTIONS.append(COL_NAME)
    PREFIX_OF[COL_NAME] = "ENV_"


# ==========================================================================
# 4. 머티리얼
# ==========================================================================
def build_concrete_material():
    """콘크리트 바닥.

    균일한 회색이면 노면(아스팔트 0.03~0.11)과 밝기만 다른 같은 재질로 보인다.
    스케일이 다른 노이즈 2장으로 (1) 수십 cm 단위 얼룩·물자국, (2) mm 단위
    미세 입자를 만들고 같은 필드로 러프니스와 범프까지 흔든다.
    """
    mat, nt, bsdf = env_reset_material("MAT_ENV_Concrete")

    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-1180, 0)

    n_mac = nt.nodes.new("ShaderNodeTexNoise")       # 넓은 얼룩
    n_mac.location = (-960, 220)
    _set_input(n_mac, "Scale", 1.6)
    _set_input(n_mac, "Detail", 4.0)
    _set_input(n_mac, "Roughness", 0.58)

    n_fine = nt.nodes.new("ShaderNodeTexNoise")      # 미세 입자
    n_fine.location = (-960, -220)
    _set_input(n_fine, "Scale", 62.0)
    _set_input(n_fine, "Detail", 5.0)
    _set_input(n_fine, "Roughness", 0.60)

    nt.links.new(tc.outputs["Object"], n_mac.inputs["Vector"])
    nt.links.new(tc.outputs["Object"], n_fine.inputs["Vector"])

    # Mix 노드는 3.x/4.x 소켓 이름이 갈린다. Math 로 섞으면 버전 안전하다.
    m_a = nt.nodes.new("ShaderNodeMath")
    m_a.location = (-720, 220)
    m_a.operation = 'MULTIPLY'
    m_a.inputs[1].default_value = 0.72
    nt.links.new(n_mac.outputs["Fac"], m_a.inputs[0])

    m_b = nt.nodes.new("ShaderNodeMath")
    m_b.location = (-720, -220)
    m_b.operation = 'MULTIPLY'
    m_b.inputs[1].default_value = 0.28
    nt.links.new(n_fine.outputs["Fac"], m_b.inputs[0])

    m_sum = nt.nodes.new("ShaderNodeMath")
    m_sum.location = (-520, 0)
    m_sum.operation = 'ADD'
    nt.links.new(m_a.outputs["Value"], m_sum.inputs[0])
    nt.links.new(m_b.outputs["Value"], m_sum.inputs[1])

    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-300, 140)
    cr = ramp.color_ramp
    cr.elements[0].position = 0.0
    cr.elements[0].color = (CONCRETE_LO, CONCRETE_LO, CONCRETE_LO * 1.03, 1.0)
    cr.elements[1].position = 1.0
    cr.elements[1].color = (CONCRETE_HI, CONCRETE_HI, CONCRETE_HI * 1.02, 1.0)
    mid = cr.elements.new(0.48)
    mid.color = (CONCRETE_MID, CONCRETE_MID, CONCRETE_MID * 1.02, 1.0)
    nt.links.new(m_sum.outputs["Value"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

    mr = nt.nodes.new("ShaderNodeMapRange")          # 마른 자국처럼 러프니스 편차
    mr.location = (-300, -200)
    _set_input(mr, "From Min", 0.25)
    _set_input(mr, "From Max", 0.75)
    _set_input(mr, "To Min", 0.72)
    _set_input(mr, "To Max", 0.96)
    nt.links.new(n_mac.outputs["Fac"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], bsdf.inputs["Roughness"])

    bump = nt.nodes.new("ShaderNodeBump")            # 지오메트리 없이 미세 요철
    bump.location = (140, -260)
    _set_input(bump, "Strength", 0.18)
    _set_input(bump, "Distance", 0.004)
    nt.links.new(m_sum.outputs["Value"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    _set_input(bsdf, "Metallic", 0.0)
    _set_input(bsdf, "Specular IOR Level", 0.30)     # 4.x
    _set_input(bsdf, "Specular", 0.30)               # 3.x
    mat.diffuse_color = (CONCRETE_MID, CONCRETE_MID, CONCRETE_MID, 1.0)
    return mat


def build_wall_material():
    """도장 벽.

    단색 흰벽은 배경이 종이처럼 보인다. 두 가지만 준다:
      (1) 바닥 쪽이 어둡고 천장 쪽이 밝은 세로 그라디언트 — 실내 조명의 자연스러운 결과
      (2) 넓은 스케일의 얼룩 — 도장면 얼룩/때
    로컬 Z 를 쓰므로 벽 오브젝트의 원점(바닥 중앙) 기준 0~높이 로 매핑된다.
    """
    mat, nt, bsdf = env_reset_material("MAT_ENV_Wall")

    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-1180, 0)

    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (-960, -180)
    nt.links.new(tc.outputs["Object"], sep.inputs["Vector"])

    grad = nt.nodes.new("ShaderNodeMapRange")
    grad.location = (-760, -180)
    _set_input(grad, "From Min", 0.0)
    _set_input(grad, "From Max", WALL_TOP)
    _set_input(grad, "To Min", 0.0)
    _set_input(grad, "To Max", 1.0)
    nt.links.new(sep.outputs["Z"], grad.inputs["Value"])

    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.location = (-960, 220)
    _set_input(noise, "Scale", 2.1)
    _set_input(noise, "Detail", 3.0)
    _set_input(noise, "Roughness", 0.50)
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])

    m_g = nt.nodes.new("ShaderNodeMath")
    m_g.location = (-540, -180)
    m_g.operation = 'MULTIPLY'
    m_g.inputs[1].default_value = 0.68
    nt.links.new(grad.outputs["Result"], m_g.inputs[0])

    m_n = nt.nodes.new("ShaderNodeMath")
    m_n.location = (-540, 220)
    m_n.operation = 'MULTIPLY'
    m_n.inputs[1].default_value = 0.32
    nt.links.new(noise.outputs["Fac"], m_n.inputs[0])

    m_sum = nt.nodes.new("ShaderNodeMath")
    m_sum.location = (-340, 20)
    m_sum.operation = 'ADD'
    nt.links.new(m_g.outputs["Value"], m_sum.inputs[0])
    nt.links.new(m_n.outputs["Value"], m_sum.inputs[1])

    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-120, 140)
    cr = ramp.color_ramp
    cr.elements[0].position = 0.05
    cr.elements[0].color = (WALL_ALBEDO_LO, WALL_ALBEDO_LO,
                            min(1.0, WALL_ALBEDO_LO * 1.02), 1.0)
    cr.elements[1].position = 0.95
    cr.elements[1].color = (WALL_ALBEDO_HI, WALL_ALBEDO_HI,
                            min(1.0, WALL_ALBEDO_HI * 1.01), 1.0)
    nt.links.new(m_sum.outputs["Value"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.location = (-120, -220)
    _set_input(mr, "From Min", 0.2)
    _set_input(mr, "From Max", 0.8)
    _set_input(mr, "To Min", 0.55)
    _set_input(mr, "To Max", 0.82)
    nt.links.new(noise.outputs["Fac"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], bsdf.inputs["Roughness"])

    _set_input(bsdf, "Metallic", 0.0)
    _set_input(bsdf, "Specular IOR Level", 0.28)
    _set_input(bsdf, "Specular", 0.28)
    _m = 0.5 * (WALL_ALBEDO_LO + WALL_ALBEDO_HI)
    mat.diffuse_color = (_m, _m, _m, 1.0)
    return mat


MAT_CONCRETE = build_concrete_material()
MAT_WALL     = build_wall_material()
MAT_SKIRT    = get_or_create_material("MAT_ENV_Skirt", color=SKIRT_COLOR,
                                      roughness=0.48, metallic=0.0)
MAT_CEIL     = get_or_create_material("MAT_ENV_Ceiling", color=CEIL_COLOR,
                                      roughness=0.88, metallic=0.0)
MAT_PANEL    = get_or_create_material("MAT_ENV_Panel", color=PANEL_COLOR,
                                      roughness=0.35, metallic=0.0,
                                      emission=PANEL_COLOR,
                                      emission_strength=PANEL_EMISSION)


# ==========================================================================
# 5. 바닥
# ==========================================================================
# 트레이 바닥(-0.032)보다 2 mm 아래. 완전 동일면이면 트레이 밑면과 Z-파이팅이 난다.
# 2 mm 틈은 트레이 자신에 가려 어느 카메라에서도 보이지 않는다.
floor = make_plane("ENV_Floor", FLOOR_SIZE, FLOOR_SIZE, z=FLOOR_Z,
                   col=COL_NAME, mat=MAT_CONCRETE)
no_shadow(floor)


# ==========================================================================
# 6. 벽 4면 + 걸레받이
# ==========================================================================
WALL_H = (WALL_TOP - FLOOR_Z) + WALL_OVER      # 바닥에서 천장 슬래브 안까지
_c = ROOM_HALF + WALL_T * 0.5                  # 벽 박스 중심 (안쪽 면이 ±ROOM_HALF)
_span_ns = 2.0 * ROOM_HALF + 2.0 * WALL_T      # N/S 벽이 모서리를 덮는다
_span_ew = 2.0 * ROOM_HALF

WALLS = [
    ("ENV_Wall_N", (_span_ns, WALL_T, WALL_H), (0.0,  _c,  FLOOR_Z)),
    ("ENV_Wall_S", (_span_ns, WALL_T, WALL_H), (0.0, -_c,  FLOOR_Z)),
    ("ENV_Wall_E", (WALL_T, _span_ew, WALL_H), (_c,   0.0, FLOOR_Z)),
    ("ENV_Wall_W", (WALL_T, _span_ew, WALL_H), (-_c,  0.0, FLOOR_Z)),
]
for nm, sz, lc in WALLS:
    env_box(nm, sz, lc, MAT_WALL)

# 걸레받이 — 벽면에서 실내로 22 mm 튀어나오고 벽 안으로 4 mm 파묻는다.
# 파묻지 않으면 뒷면이 벽 안쪽 면과 완전 동일면이 되어 그 띠 전체가 깜빡인다.
_sk = ROOM_HALF - SKIRT_T * 0.5 + SKIRT_EMBED
SKIRTS = [
    ("ENV_Skirt_N", (_span_ew, SKIRT_T, SKIRT_H), (0.0,  _sk, FLOOR_Z)),
    ("ENV_Skirt_S", (_span_ew, SKIRT_T, SKIRT_H), (0.0, -_sk, FLOOR_Z)),
    ("ENV_Skirt_E", (SKIRT_T, _span_ew, SKIRT_H), (_sk,  0.0, FLOOR_Z)),
    ("ENV_Skirt_W", (SKIRT_T, _span_ew, SKIRT_H), (-_sk, 0.0, FLOOR_Z)),
]
for nm, sz, lc in SKIRTS:
    env_box(nm, sz, lc, MAT_SKIRT)


# ==========================================================================
# 7. 천장 + 이미시브 패널 (+ 짝 광원)
# ==========================================================================
# 평면 대신 두께 있는 박스로 만든다. make_plane 은 법선이 +Z 라 아래에서 보면
# 뒷면이 보인다. 박스는 아랫면 법선이 -Z 라 실내에서 정상적으로 셰이딩된다.
env_box("ENV_Ceiling", (FLOOR_SIZE, FLOOR_SIZE, CEIL_T), (0.0, 0.0, CEIL_Z), MAT_CEIL)

panels, lamps = [], []
_i = 0
for gy in PANEL_YS:
    for gx in PANEL_XS:
        _i += 1
        pnm = "ENV_CeilPanel_%02d" % _i
        env_box(pnm, (PANEL_SX, PANEL_SY, PANEL_H), (gx, gy, PANEL_BOT_Z), MAT_PANEL)
        panels.append(pnm)

        if CEIL_LAMP_ENABLE:
            lnm = "ENV_CeilLamp_%02d" % _i
            ld = bpy.data.lights.new(lnm, 'AREA')
            ld.shape = 'RECTANGLE'
            ld.size = PANEL_SX
            ld.size_y = PANEL_SY
            ld.energy = CEIL_LAMP_POWER
            ld.color = CEIL_LAMP_COLOR
            # 그림자를 끈다: 6개가 각자 그림자를 던지면 건물 밑이 지저분해지고
            # 프레임당 렌더 시간이 눈에 띄게 늘어난다. 이 램프들의 역할은 앰비언트다.
            ld.use_shadow = False
            lo = bpy.data.objects.new(lnm, ld)
            lo.location = (gx, gy, PANEL_BOT_Z - 0.002)   # 패널 바로 아래에서 아래로
            lo.rotation_euler = (0.0, 0.0, 0.0)           # AREA 기본 방향 = -Z
            link_to(lo, COL_NAME)
            lamps.append(lnm)


# ==========================================================================
# 8. QA — 카메라 여유와 기하 일관성을 수치로 확인한다
# ==========================================================================
wall_margin = ROOM_HALF - CAM_MAX_R
ceil_margin = CEIL_Z - CAM_MAX_Z
if wall_margin < 0.5:
    WARN.append("벽 여유 %.3f m — 오비탈 컷에서 카메라가 벽에 붙는다. ROOM_HALF 를 키워라"
                % wall_margin)
if ceil_margin < 0.5:
    WARN.append("천장 여유 %.3f m — 카메라가 천장을 뚫는다. CEIL_Z 를 올려라" % ceil_margin)
if FLOOR_Z >= TRAY_BOTTOM_Z:
    WARN.append("ENV_Floor 가 트레이 바닥보다 높거나 같다 — Z-파이팅")
if PANEL_BOT_Z >= CEIL_Z + 1e-6:
    WARN.append("패널이 천장 슬래브 안에 파묻혔다")

# 90_camera.py 의 키/필 라이트가 방 안에 들어오는지 (실측 좌표 기준)
for _nm, _p in (("LGT_Key", (1.70, 2.45, 2.85)), ("LGT_Fill", (-2.55, -2.35, 1.75))):
    if abs(_p[0]) > ROOM_HALF or abs(_p[1]) > ROOM_HALF or _p[2] > CEIL_Z:
        WARN.append("%s 가 방 밖에 있다 %s — 벽/천장 뒤에서 비추게 된다" % (_nm, _p))

made = [o for o in bpy.data.objects if o.name.startswith("ENV_")]
n_mesh = len([o for o in made if o.type == 'MESH'])
n_lamp = len([o for o in made if o.type == 'LIGHT'])

print("[85_environment] purged=%d | ENV_ 오브젝트 %d개 (mesh %d / light %d) → %s"
      % (n_purged, len(made), n_mesh, n_lamp, COL_NAME))
print("  바닥  ENV_Floor      %.1f x %.1f m @ Z=%+.3f (트레이 바닥 %+.3f 보다 %.0f mm 아래)"
      % (FLOOR_SIZE, FLOOR_SIZE, FLOOR_Z, TRAY_BOTTOM_Z, FLOOR_EPS * 1000))
print("  벽    ENV_Wall_N/S/E/W  안쪽 면 ±%.2f m (내부 %.1f x %.1f m) / 두께 %.0f mm / 높이 %.2f m"
      % (ROOM_HALF, 2 * ROOM_HALF, 2 * ROOM_HALF, WALL_T * 1000, WALL_TOP))
print("  걸레받이 ENV_Skirt_*   높이 %.0f mm / 돌출 %.0f mm" % (SKIRT_H * 1000, SKIRT_T * 1000))
print("  천장  ENV_Ceiling    아랫면 Z=%.2f m / 슬래브 %.0f mm" % (CEIL_Z, CEIL_T * 1000))
print("  패널  ENV_CeilPanel_01~%02d  %.2f x %.2f m @ Z=%.3f / emission %.1f"
      % (len(panels), PANEL_SX, PANEL_SY, PANEL_BOT_Z, PANEL_EMISSION))
if CEIL_LAMP_ENABLE:
    print("  램프  ENV_CeilLamp_01~%02d  AREA %.0f W x%d = %.0f W (그림자 OFF) "
          "— 끄려면 CEIL_LAMP_ENABLE=False"
          % (len(lamps), CEIL_LAMP_POWER, len(lamps), CEIL_LAMP_POWER * len(lamps)))
else:
    print("  램프  없음 (CEIL_LAMP_ENABLE=False) — 패널은 화면에 보일 때만 GI 로 기여한다")
print("  그림자 캐스트: 모든 ENV_ = OFF  ← 저고도 SUN 림 라이트(el 10°/15°)가 "
      "벽에 막히는 것을 막는다")
print("  카메라 여유: 벽까지 %.3f m (최대반경 %.3f) / 천장까지 %.3f m (최대높이 %.3f)"
      % (wall_margin, CAM_MAX_R, ceil_margin, CAM_MAX_Z))

print("  ---- 90_camera.py 반영 제안 (LIGHT_ADJUST — 이 스크립트는 적용하지 않는다) ----")
for k, v in LIGHT_ADJUST.items():
    print("    %-14s %7.2f → %7.2f   %s" % (k, v["from"], v["to"], v["why"]))
print("    %s" % LIGHT_ADJUST_NOTE_BRIGHT)
print("    %s" % LIGHT_ADJUST_NOTE_DARK)
print("    적용 전 반드시 단일 프레임 테스트 렌더로 확인할 것. 전체 렌더는 그다음이다.")

for w in WARN:
    print("  [경고] %s" % w)
if not WARN:
    print("  [OK] 경고 없음")
