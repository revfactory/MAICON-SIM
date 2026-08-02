# -*- coding: utf-8 -*-
"""
90_camera.py — 카메라 리그 · 라이팅 · 컷 편집 (cinematographer 산출)

씬에 드론(10_Drone) · 화재 건물 2동(SEC_02 / SEC_09) · QR 아군표식(QRM_01)이
추가되어 컷 시트를 13컷으로 재구성했다.

    CAM_Orbital     피벗 회전 + Track To. 화재 조감(컷3) / 피니시 로우 히어로(컷13)
    CAM_Chase       PATH_Main 을 호장 지연 추종하는 리그의 자식
    CAM_Slowmo      체크포인트 옆 저각 고정 + Track To(UGV) + 렌즈 푸시인
    CAM_FPV         UGV_Cam 앵커에 부모 고정한 1인칭
    CAM_Avoid       회피 이벤트 전용 저각 고정 + Track To(UGV)   ← 신규
    CAM_Drone       DRN_Cam 에 부모 고정한 나디르(-Z) 드론 시점    ← 신규 (과제 시점)
    CAM_DroneExt    드론 외부 샷 (이륙 / 화재 촬영 호버)          ← 신규

    LGT_Key / LGT_Fill / LGT_Rim_A / LGT_Rim_B
    LGT_Fire_02 / LGT_Fire_09   화재 반사광 POINT (깜박임)        ← 신규
    LGT_QR_Fill                 QR 아군표식 전용 SPOT 필           ← 신규
    + QR_MAT_* 이미시브 부스트                                    ← 신규

--------------------------------------------------------------------------
프레임 값을 고치는 곳
--------------------------------------------------------------------------
1) spec/timeline.json (UGV) 과 spec/drone_timeline.json (드론)에서 자동으로 읽는다.
   두 파일이 갱신되면 이 스크립트를 그대로 재실행하면 컷이 실측값으로 재계산된다.
2) 없으면 아래 FALLBACK / DP_FALLBACK 의 실측 인계값을 쓴다.

컷 타이밍만 바꾸려면 `CUT_PLAN` 만 고친다. 카메라 애니메이션은 건드리지 않는다.
카메라 위치/렌즈는 `--- 룩 파라미터 ---` 블록만 고친다.

--------------------------------------------------------------------------
축소 모형을 크게 보이게 하는 두 원칙 (이 파일 전체의 근거)
--------------------------------------------------------------------------
* 얕은 피사계 심도 = 모형 신호 → DOF 는 전부 끈다 (FPV_USE_DOF 주석 참조).
* 높은 시점 = 모형 신호 → 모든 지상 카메라를 노면 0.058~0.86 m 에 두고
  초점거리를 30~44 mm 로 쓴다. 광각(<28 mm)은 쓰지 않는다.
  예외는 CAM_Drone(나디르 28 mm) 하나다 — 근거는 8절에 적었다.
"""

import bpy
import math
import os
import json
import mathutils

WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
exec(open(os.path.join(WORKSPACE, "scripts", "00_common.py")).read())

scene = bpy.context.scene


# ==========================================================================
# 1. 프레임 상수  — >>> 실측 갱신 지점 <<<
# ==========================================================================
TIMELINE_PATH = os.path.join(WORKSPACE, "spec", "timeline.json")
DRONE_TL_PATH = os.path.join(WORKSPACE, "spec", "drone_timeline.json")

# timeline.json 이 없을 때만 쓰는 값 (motion-director 실측 인계 기준, 2차 갱신본)
FALLBACK = {
    "fps": 30,
    "total_frames": 720,                      # 24.0 s
    "events": {"START": 1, "ALPHA": 75, "BRAVO": 364, "CHARLIE": 568, "FINISH": 695},
}
# drone_timeline.json 이 없을 때만 쓰는 드론 8구간
DP_FALLBACK = {
    "IDLE": (1, 48), "TAKEOFF": (48, 110), "OUTBOUND": (110, 300),
    "SHOOT_2": (300, 360), "TRANSIT": (360, 500), "SHOOT_9": (500, 560),
    "RETURN": (560, 680), "LAND": (680, 720),
}
# 회피 이벤트(슬로모 후보) — timeline.json.avoidance_events 가 있으면 덮어쓴다
AV_FALLBACK = {
    "pothole_1": (381, 419, 447), "barrier_1": (394, 429, 453),
    "pothole_2": (573, 596, 616), "barrier_2": (668, 695, 720),
}


def _load_json(path, label):
    if not os.path.exists(path):
        return None, "%s 없음" % label
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp), "measured (%s)" % label
    except Exception as e:
        return None, "%s 파싱 실패(%s)" % (label, e)


TL, TL_SRC = _load_json(TIMELINE_PATH, "timeline.json")
DTL, DTL_SRC = _load_json(DRONE_TL_PATH, "drone_timeline.json")

if TL is not None:
    FPS = int(TL.get("fps", FALLBACK["fps"]))
    TOTAL = int(TL.get("total_frames", FALLBACK["total_frames"]))
    EV = {e["name"]: int(e["frame"]) for e in TL.get("events", [])}
    for k, v in FALLBACK["events"].items():
        EV.setdefault(k, v)
    SEG = [(s["name"], int(s["frame_start"]), int(s["frame_end"]))
           for s in TL.get("segments", [])]
    AV = {a["name"]: (int(a["frame_enter"]), int(a["frame_apex"]), int(a["frame_exit"]))
          for a in TL.get("avoidance_events", [])}
    AVX = {a["name"]: a for a in TL.get("avoidance_events", [])}
else:
    FPS, TOTAL = FALLBACK["fps"], FALLBACK["total_frames"]
    EV, SEG, AVX = dict(FALLBACK["events"]), [], {}
    AV = dict(AV_FALLBACK)
if not AV:
    AV = dict(AV_FALLBACK)

if DTL is not None:
    DP = {p["name"]: (int(p["frame_start"]), int(p["frame_end"]))
          for p in DTL.get("phases", [])}
    SHOOT = {s["tag"]: s for s in DTL.get("shoot", [])}
    for k, v in DP_FALLBACK.items():
        DP.setdefault(k, v)
else:
    DP, SHOOT = dict(DP_FALLBACK), {}

scene.frame_start = 1
scene.frame_end = TOTAL
scene.render.fps = FPS
scene.render.resolution_x = 1920           # world_to_camera_view 화각 계산에 필요
scene.render.resolution_y = 1080

REF_TOTAL = 720.0                          # 아래 절대 프레임들이 설계된 기준 길이


def A(f):
    """절대 프레임. TOTAL 이 720 에서 바뀌면 비례 환산한다(구도 유지)."""
    if TOTAL == int(REF_TOTAL):
        return int(f)
    return max(1, min(TOTAL, int(round(f * TOTAL / REF_TOTAL))))


# ==========================================================================
# 2. 룩 파라미터
# ==========================================================================
CLIP_START = 0.005      # 실측 스케일 필수. 기본 0.1 m 면 근접 샷이 잘린다
CLIP_END = 60.0         # 오비탈 반경 4.3 m + 방(±5.5 m) 벽까지 담는다

# --- 오비탈 ---------------------------------------------------------------
# (프레임, 피벗x, 피벗y, 반경, 높이, 각도deg, 렌즈mm)
# 온스크린 구간은 컷3(f111~168) 과 컷13(f656~720) 뿐이다. 그 사이는 오프스크린 이동.
#
# ★ 컷3 은 "화재 2동 + 드론 이동"을 한 프레임에 담는 조감이다. 동쪽 외곽 az≈0 에서
#   SEC_02(0.03, 1.09) 는 광축 14°, SEC_09(1.3, -1.15) 는 20~24° 에 온다.
#   32 mm 의 수평 반화각이 29.4° 이므로 둘 다 들어온다. 이보다 길게 쓰면 SEC_09 가
#   프레임 밖으로 나간다 — 렌즈를 올리려면 반경을 함께 키워야 한다.
# ★ 높이 0.80→0.64 로 내려간다. 이전 버전(1.05)보다 낮춰 모형 느낌을 줄였다.
ORBITAL_KEYS = [
    (  1,  0.00,  0.00, 4.35, 0.86,  -8.0, 32.0),   # 오프스크린 (컷3 진입 준비)
    (111,  0.00,  0.00, 4.30, 0.80,  -2.0, 32.0),   # 컷3 시작: 동쪽 외곽 화재 조감
    (168,  0.00,  0.00, 4.05, 0.64,  10.0, 32.0),   # 컷3 끝  : UGV 가 프레임 우측으로 이탈
    (420,  0.90, -1.05, 2.60, 0.55,  45.0, 36.0),   # 오프스크린 이동 (남동 회랑)
    (656,  1.50, -1.62, 0.95, 0.34,  55.0, 40.0),   # 컷13 시작: 하단 직선 재가속을 옆에서
    (720,  2.23, -1.68, 0.66, 0.24,  72.0, 44.0),   # 컷13 끝  : FINISH 로우 히어로
]
ORBITAL_AIM_Z = 0.12

# --- 체이스 ---------------------------------------------------------------
# 차량에 직접 부모 고정하면 코너에서 화면이 급회전해 어지럽다.
# PATH_Main 을 따라가되 호장 기준으로 CHASE_LAG_M 만큼 뒤처지는 리그를 쓴다.
CHASE_LENS = 40.0
CHASE_LAG_M = 0.42        # 경로 호장 기준 지연 거리 (Follow Path offset 으로 환산)
CHASE_BACK = 0.12         # 리그 로컬 -X (추가 후방 오프셋)
CHASE_UP = 0.13           # 리그 로컬 +Z (노면 위 높이)
CHASE_AIM = (0.02, 0.0, 0.05)   # UGV_Root 로컬 조준점
CHASE_SHAKE_POS = 0.0035  # m. Track To 카메라는 회전 노이즈가 무시되므로 위치로 준다

# --- 슬로모 (체크포인트) ---------------------------------------------------
# 렌즈 근거: 시야폭 = 36 * 거리 / 렌즈(mm). 통과 최근접이 0.36~0.51 m 이므로
# 28 mm 면 시야폭 0.46~0.66 m 로 차량(전장 0.2 m)이 화면의 30~43% 를 차지하고
# 체크포인트 표식과 주변 구조물이 함께 들어온다. 34 mm 로 밀어 클로즈업 마무리.
SLOWMO_LENS = (28.0, 34.0)
SLOWMO_POS = {
    # ALPHA f75 (-1.147, 1.630) — 상단 회랑 남쪽. SEC_1(-0.45,1.09) 풋프린트에서
    # 0.318 m, OBJ_1 박격포에서 0.283 m 떨어졌다. 이보다 동쪽으로 옮기면 SEC_1 에
    # 카메라가 파묻힌다(이전 -0.66,1.24 는 여유 0.067 m 였다).
    "ALPHA":   (-0.92,  1.28, 0.070),
    # BRAVO f364 (-0.391, -0.130) — 최저속 0.29 m/s 헤어핀. 슬로모 최적
    "BRAVO":   (-0.70, -0.50, 0.065),
    # CHARLIE f568 (-1.553, -1.639) — 코너 탈출 + 포트홀2 진입(f573~)을 같은
    # 프레임에서 잇기 위해 두 지점 사이(포트홀2 로부터 0.40 m)에 놓았다.
    "CHARLIE": (-1.20, -1.24, 0.070),
    "FINISH":  (2.05, -1.35, 0.075),    # 정의만. 기본 컷 시트에서는 미사용
}
SLOWMO_AIM = (0.0, 0.0, 0.045)          # UGV_Root 로컬 조준점

# --- 회피 전용 (신규) -----------------------------------------------------
# 슬로모와 같은 방식(고정 위치 + Track To(UGV) + 렌즈 푸시인)이지만 별도 오브젝트다.
# 컷7(BRAVO 슬로모) 바로 뒤에 컷8 이 붙으므로 같은 카메라를 연속으로 쓸 수 없다.
AVOID_POS = {
    # 컷8: 포트홀1(-1.03, 0.15) 과 배리어1(-1.03, 0.59) 사이 '게이트'를 남쪽에서.
    #      UGV 는 f421 에 정점(비킴 0.220 m), f429 에 배리어 정점을 지난다.
    #      카메라-차량 거리 0.63~0.85 m, 30 mm 시야폭 0.76~1.02 m → 장애물 2개가
    #      차량과 함께 프레임에 들어온다.
    "GATE":     ((-1.15, -0.28, 0.062), (30.0, 38.0)),
    # 컷12: 포트홀2(-0.88, -1.48) 바로 옆(0.31 m). 차량은 컷 시작 0.46 m 에서
    #       1.93 m 까지 멀어진다 — 이 '멀어짐' 자체가 재가속(0.60→1.18 m/s)의
    #       시각적 증거다. 그래서 렌즈를 30→50 mm 로 크게 밀어 차량이 화면에서
    #       40%→14% 로 줄어드는 폭을 완충한다.
    #       (남쪽 회랑 안쪽 (0.05,-1.20)은 SEC_8 풋프린트 내부라 못 쓴다.)
    "POTHOLE2": ((-0.72, -1.22, 0.058), (30.0, 50.0)),
}

# --- FPV ------------------------------------------------------------------
FPV_LENS = 35.0
FPV_CLIP_START = 0.004    # UGV_Cam 은 렌즈 팁보다 2 mm 앞. 0.005 초과면 하우징에 잘린다
FPV_CLIP_END = 40.0
# DOF: 이 스케일에서 f/2.8 은 피사계 심도가 3 cm 다 (35 mm, 0.5 m 거리 기준
# 0.485~0.517 m). 그게 바로 틸트시프트 = 장난감 효과다. 그래서 기본값은 끔.
FPV_USE_DOF = False
FPV_DOF_FSTOP = 22.0
FPV_DOF_DISTANCE = 0.85
FPV_SHAKE_ROT = (0.0080, 0.0100, 0.0060)   # pitch / yaw / roll (rad)
FPV_SHAKE_UP = 0.0010

# --- 드론 나디르 (신규) ---------------------------------------------------
# DRN_Cam 에 부모 고정, 로컬 변환 0. 시점을 바꾸려면 카메라가 아니라 DRN_Cam 을
# 옮긴다(asset-modeler 소관).
#
# ★ 28 mm 인 이유 (35 mm 규칙의 유일한 예외):
#   SHOOT_2 호버는 지붕 위 0.59 m 에 불과하다. 화재동 상단 모서리가 광축에서
#   tan 0.371 (수직) 지점에 오므로, 세로 반화각이 0.371 이상이어야 한다.
#   f <= 10.125/0.371 = 27.3 mm. 35 mm(0.289) 로 찍으면 건물 위쪽이 잘려나간다.
#   나디르 뷰는 지평선이 없어 '내려다보는 각도 = 모형' 신호가 성립하지 않으므로
#   여기서 광각을 써도 축소 모형처럼 보이지 않는다. 지상 카메라에는 쓰지 않는다.
DRONE_CAM_LENS = 28.0
DRONE_CAM_CLIP_START = 0.004
DRONE_CAM_CLIP_END = 40.0

# --- 드론 외부 샷 (신규) --------------------------------------------------
# 컷 사이는 오프스크린이므로 CONSTANT 키로 순간이동한다.
# pos/lens 는 (컷 내 진행비율 0~1, 값).
DRONEEXT_SHOTS = {
    # 컷1 f1~66: 헬리패드(-1.95, 0.80) 남동쪽 0.79 m, 노면 0.085 m 저각.
    #   f1~47  기체 정지(로터 아이들) + 배경에서 UGV 가 START 를 떠난다
    #   f48~   수직 상승 시작. 카메라도 0.085→0.185 m 로 함께 크레인 업.
    #   START(-2.35, 1.33) 이 헬리패드와 거의 같은 방위(133°)에 있어 드론 뒤로
    #   UGV 발진이 겹쳐 들어온다 — 두 기체를 한 컷에서 소개한다.
    #   ★ aim_follow 0.35: 조준점이 드론 고도를 100% 따라가면 드론이 화면 한가운데
    #     고정되어 '오르는 느낌'이 사라진다(실측: y +2.1 → +2.1). 35% 만 따라가면
    #     드론이 프레임 안에서 실제로 올라간다(y +2.1 → +5.9, 세로 반폭 10.1).
    "TAKEOFF": dict(
        pos=[(0.00, (-1.34, 0.30, 0.085)), (1.00, (-1.46, 0.17, 0.185))],
        lens=[(0.00, 40.0), (1.00, 38.0)],
        aim="drone", aim_bias=(0.0, 0.0, -0.045), aim_follow=0.35, aim_samples=9),
    # 컷10 f500~559: SHOOT_9 호버. 드론(1.30,-0.95,1.05) + SEC_09(1.30,-1.15,h0.40)
    #   + 연기 기둥(정점 0.757) 을 한 프레임에.
    #   ★ 남쪽 트레이 밖 1.75 m 에서 잡는 이유: 드론(z 1.05)과 건물 바닥(z 0)의
    #     수직 시각 스팬은 거리에 반비례한다. 1.0 m 에서 찍으면 48°가 되어 어떤
    #     렌즈로도 둘을 못 담는다. 1.75 m 로 물리면 32°로 줄어 32 mm(35.2°)에 들어온다.
    #   시선이 트레이 가장자리(y=-1.75, 높이 0.05)를 넘는지 확인함: 교차점 z=0.16.
    #   횡이동 0.36 m 로 시차만 준다. 종이동/줌은 넣지 않는다 — 가까워지면
    #   드론(z 1.05)이 위쪽 프레임 밖으로 나간다(실측: x 1.52 에서 건물 우하단 이탈).
    "SHOOT_9": dict(
        pos=[(0.00, (1.10, -2.88, 0.46)), (1.00, (1.46, -2.86, 0.45))],
        lens=[(0.00, 32.0), (1.00, 32.0)],
        aim="fixed", aim_pos=(1.33, -1.14, 0.50)),
}

# --- 라이팅 ---------------------------------------------------------------
# 값은 85_environment.py 실행 후 검증된 룩(output/stills)을 그대로 유지한다.
# 85 가 제안한 LIGHT_ADJUST(430/115/3.3/2.1/0.60)는 적용하지 않았다 —
# 현재 값으로 이미 전체 렌더가 통과했고, 이번 작업은 노출이 아니라
# QR 가독성과 화재 발광의 씬 기여가 과제이기 때문이다. 필요하면 여기만 바꾼다.
KEY_POWER, KEY_SIZE = 520.0, 3.2
KEY_POS, KEY_AIM = (1.70, 2.45, 2.85), (0.0, 0.10, 0.15)
KEY_COLOR = (0.94, 0.965, 1.0)

FILL_POWER, FILL_SIZE = 170.0, 4.6
FILL_POS, FILL_AIM = (-2.55, -2.35, 1.75), (0.0, 0.0, 0.20)
FILL_COLOR = (1.0, 0.955, 0.90)

# 림은 2개다. 하나만 두면 오비탈이 반 바퀴 도는 동안 스카이라인이 사라진다.
RIM_A = dict(az=200.0, el=10.0, energy=2.9, color=(1.0, 0.845, 0.63), angle=0.012)
RIM_B = dict(az=40.0,  el=15.0, energy=1.8, color=(0.68, 0.80, 1.0), angle=0.016)
SUN_DIST = 8.0

WORLD_COLOR = (0.045, 0.055, 0.078)
WORLD_STRENGTH = 1.0

# --- 화재 반사광 (신규) ---------------------------------------------------
# 화염창/옥상 화염은 이미시브 지오메트리다. EEVEE 에서 이미시브는 화면에 보일 때만
# 스크린 스페이스 GI 로 주변에 기여하므로, 광원이 없으면 주변 벽에 주황이 전혀
# 얹히지 않고 '스티커'처럼 보인다. 실제 POINT 를 하나씩 넣어 물들인다.
#
# 40_sectors.py 가 이미 SEC_0N_Fire_Light(2.6 W x intensity)를 만든다. 그것은
# 화염 자체의 자기조명 수준이라 주변까지 못 물들인다. 여기 것은 '환경 기여'용이며
# 접두사가 달라(LGT_) 서로 purge 하지 않는다 — 합산 조명이 된다.
FIRE_LIGHT = True
FIRE_POWER = 9.0            # W. intensity(SEC_02 1.0 / SEC_09 0.85)를 곱한다
FIRE_COLOR = (1.0, 0.44, 0.12)
FIRE_Z_OVER_ROOF = 0.05     # 지붕 위 이 높이에 광원을 둔다 (지붕과 주변을 함께)
FIRE_SOFT = 0.06            # shadow_soft_size. 불꽃은 점광원이 아니다
FIRE_CUTOFF = 1.60          # m. 영향 반경을 잘라 먼 건물이 주황으로 물드는 것을 막는다
FIRE_FLICKER = 0.22         # 강도 대비 깜박임 진폭
FIRE_FLICKER_SCALE = 2.2    # 작을수록 빠르다

# --- QR 아군표식 가독성 (신규) --------------------------------------------
# 문제: QRM_01(-1.50, 1.46)의 판 법선(로컬 +X)이 yaw -2.990 rad → 서남서를 향한다.
#       LGT_Key 는 북동(1.70, 2.45, 2.85)에 있어 직사광이 판 뒷면에만 닿는다.
#       AgX 는 어두운 영역을 더 눌러 흑백 패턴이 통째로 뭉갠다.
#
# 대응 (둘 다 쓴다. 근거가 다르다):
#  (1) QR_MAT_* 이미시브 부스트 — 텍스처 Color 를 Emission Color 에 그대로 물려
#      **패턴 모양 그대로** 발광시킨다. 검은 모듈은 0 이라 그대로 검게 남으므로
#      대비가 보존된다. 필 라이트만 쓰면 검은 모듈에도 스펙큘러가 얹혀 대비가 준다.
#      또한 시점 독립적이라 FPV·체이스·조감 어느 컷에서도 동일하게 읽힌다.
#  (2) LGT_QR_Fill SPOT — 이미시브만 있으면 판이 '라이트박스'가 되어 프레임/스탠드가
#      까맣게 남고 입체감이 사라진다. 판 정면 0.36 m 에서 좁은 콘으로 흰 테두리와
#      프레임에만 형태감을 준다. 그림자는 끈다(판이 노면에 이중 그림자를 만든다).
QR_EMISSION = 0.25          # 0.15~0.30 권장 구간의 중상단
QR_FILL = True
QR_FILL_POWER = 2.2         # W
QR_FILL_DIST = 0.36         # 판 법선 방향 거리
QR_FILL_UP = 0.20           # 판 중심 위 높이
QR_FILL_CONE = math.radians(46.0)
QR_FILL_COLOR = (1.0, 0.98, 0.95)


# ==========================================================================
# 3. 컷 플랜  — 13컷 / 720프레임 / 24.0 s
# ==========================================================================
MIN_CUT = 40          # 1.33 s. 이보다 짧으면 무엇을 보는지 인식하기 전에 넘어간다
CP_LEAD = 8           # 체크포인트 컷은 통과 프레임의 8프레임 전에 시작한다

# at = ("abs", frame) | ("cp", 이름[, 오프셋]) | ("dp", 드론구간[, 오프셋])
CUT_PLAN = [
    dict(cam="CAM_DroneExt", at=("abs", 1),            lock=True,  shot="TAKEOFF",
         label="오프닝 — 헬리패드 저각. 로터 아이들 → f48 수직 이륙. 배경에 UGV 발진"),
    dict(cam="CAM_Slowmo",   at=("cp", "ALPHA"),       lock=True,  aim="ALPHA",
         label="ALPHA 통과 히어로 (f%d, 리드 +8) — 저각 0.068 m" % EV.get("ALPHA", 75)),
    dict(cam="CAM_Orbital",  at=("abs", 111),          lock=True,
         label="화재 조감 — SEC_02 + SEC_09 연기 기둥 2개 동시 프레임, 드론 상승 통과"),
    dict(cam="CAM_Chase",    at=("abs", 169),          lock=False,
         label="EAST_SWEEP 체이스 — 우측 코너 연속 감속"),
    dict(cam="CAM_FPV",      at=("abs", 229),          lock=False,
         label="CENTER_CORRIDOR 1인칭 — 중앙 십자 회랑, 정면에 SEC_02 화재"),
    dict(cam="CAM_Drone",    at=("dp", "SHOOT_2"),     lock=True,
         label="★ 드론 나디르 시점 — SEC_02 화재 촬영. 과제(드론 촬영 추론) 그 자체"),
    dict(cam="CAM_Slowmo",   at=("cp", "BRAVO"),       lock=True,  aim="BRAVO",
         label="BRAVO 헤어핀 히어로 (f%d, 리드 +8) — 최저속 0.29 m/s" % EV.get("BRAVO", 364)),
    dict(cam="CAM_Avoid",    at=("abs", 396),          lock=True,  aim="GATE",
         label="회피 하이라이트 — 포트홀1 정점 f419 + 배리어1 정점 f429 (한 컷 2이벤트)"),
    dict(cam="CAM_Chase",    at=("abs", 460),          lock=False,
         label="WEST_TRAVERSE 체이스 — 좌측 회랑 하강"),
    dict(cam="CAM_DroneExt", at=("dp", "SHOOT_9"),     lock=True,  shot="SHOOT_9",
         label="드론 화재 촬영 외부 샷 — 드론 + SEC_09 화염/연기 동시 프레임"),
    dict(cam="CAM_Slowmo",   at=("cp", "CHARLIE"),     lock=True,  aim="CHARLIE",
         label="CHARLIE 통과 히어로 (f%d, 리드 +8) + 포트홀2 진입/감속"
               % EV.get("CHARLIE", 568)),
    dict(cam="CAM_Avoid",    at=("abs", 600),          lock=True,  aim="POTHOLE2",
         label="포트홀2 회피 슬로모 — 이탈 스윙 + 재가속 0.60→1.18 m/s"),
    dict(cam="CAM_Orbital",  at=("abs", 656),          lock=True,
         label="피니시 로우 오비탈 — FINISH 통과 + 배리어2 제동 + 정지 홀드"),
]

QA_STRIDE = 6         # 컷 QA 샘플 간격(프레임). 0 이면 QA 생략
QA_CLEAR_WARN = 0.06  # m. 이보다 가까우면 관통 위험으로 경고


print("[90_camera] UGV: %s | 드론: %s | TOTAL=%d @%dfps" % (TL_SRC, DTL_SRC, TOTAL, FPS))
print("  체크포인트  ALPHA %d / BRAVO %d / CHARLIE %d / FINISH %d"
      % (EV["ALPHA"], EV["BRAVO"], EV["CHARLIE"], EV["FINISH"]))
print("  드론구간    TAKEOFF %s / SHOOT_2 %s / SHOOT_9 %s / LAND %s"
      % (DP["TAKEOFF"], DP["SHOOT_2"], DP["SHOOT_9"], DP["LAND"]))


# ==========================================================================
# 4. 헬퍼
# ==========================================================================
def _fcurves_of(id_block):
    """액션의 F커브 컬렉션. 4.4 슬롯(layer/strip/channelbag) 액션도 처리한다."""
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
    try:                                        # Blender 4.4+ 슬롯 액션
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


def _set_prop(owner, data_path, index, value):
    if index is None:
        setattr(owner, data_path, value)
    else:
        getattr(owner, data_path)[index] = value


def _insert(owner, data_path, index, frame):
    if index is None:
        owner.keyframe_insert(data_path, frame=int(frame))
    else:
        owner.keyframe_insert(data_path, index=index, frame=int(frame))


def bake_channel(owner, data_path, index, frames, values,
                 interp='BEZIER', handle='AUTO_CLAMPED'):
    """프레임/값 배열을 F커브에 굽는다 (bpy.ops 미사용).

    interp / handle 은 문자열 하나(전체 공통) 또는 키 개수만큼의 리스트를 받는다.
    프레임 배열은 오름차순·중복 없음이어야 한다 (호출부에서 보장).
    """
    assert len(frames) == len(values) and len(frames) > 0
    n = len(frames)
    interps = [interp] * n if isinstance(interp, str) else list(interp)
    handles = [handle] * n if isinstance(handle, str) else list(handle)

    _set_prop(owner, data_path, index, float(values[0]))
    _insert(owner, data_path, index, frames[0])
    fc = _find_fcurve(owner, data_path, index)
    if fc is None:                                   # 폴백 (F커브를 못 찾는 환경)
        for f, v in zip(frames, values):
            _set_prop(owner, data_path, index, float(v))
            _insert(owner, data_path, index, f)
        return _find_fcurve(owner, data_path, index)

    kps = fc.keyframe_points
    if len(kps) != 1:
        for f, v in zip(frames[1:], values[1:]):
            _set_prop(owner, data_path, index, float(v))
            _insert(owner, data_path, index, f)
    else:
        if n > 1:
            kps.add(n - 1)
        for i in range(n):
            kps[i].co = (float(frames[i]), float(values[i]))
    for i, kp in enumerate(kps):
        j = min(i, n - 1)
        kp.interpolation = interps[j]
        kp.handle_left_type = kp.handle_right_type = handles[j]
    fc.update()
    return fc


def bake_segments(owner, data_path, index, segments):
    """세그먼트별로 키를 굽고, 세그먼트 마지막 키를 CONSTANT 로 굳힌다.

    카메라가 컷과 컷 사이(오프스크린)에서 값을 유지하다가 다음 컷 시작에
    순간이동하게 만드는 장치다. 세그먼트 경계 키는 VECTOR 핸들로 두어
    먼 다음 키 때문에 컷 안에서 오버슈트하는 것을 막는다.
    """
    frames, values, interps, handles = [], [], [], []
    for si, seg in enumerate(segments):
        for ki, (f, v) in enumerate(seg):
            f = int(f)
            if frames and f <= frames[-1]:
                f = frames[-1] + 1
            last = (ki == len(seg) - 1)
            first = (ki == 0)
            frames.append(f)
            values.append(float(v))
            interps.append('CONSTANT' if (last and si < len(segments) - 1) else 'BEZIER')
            handles.append('VECTOR' if (first or last) else 'AUTO_CLAMPED')
    return bake_channel(owner, data_path, index, frames, values, interps, handles)


def add_noise(fc, strength, scale, phase=0.0):
    """F커브 노이즈 모디파이어. 손떨림·불꽃 깜박임을 키프레임 없이 만든다."""
    if fc is None:
        return None
    nm = fc.modifiers.new('NOISE')
    nm.strength = float(strength)
    nm.scale = float(scale)
    nm.phase = float(phase)
    for attr, val in (("blend_type", 'ADD'), ("depth", 0)):
        try:
            setattr(nm, attr, val)
        except Exception:
            pass
    return nm


def flat_fcurve(owner, data_path, index, value=0.0):
    """노이즈를 얹기 위한 값 고정 F커브 (키 2개)."""
    return bake_channel(owner, data_path, index, [1, TOTAL],
                        [value, value], interp='LINEAR', handle='VECTOR')


def aim_euler(frm, to):
    """frm 에서 to 를 보는 오일러 회전 (-Z 축이 시선, +Y 가 업)."""
    d = mathutils.Vector((to[0] - frm[0], to[1] - frm[1], to[2] - frm[2]))
    return d.to_track_quat('-Z', 'Y').to_euler()


def new_empty(name, kind='PLAIN_AXES', size=0.05, loc=(0.0, 0.0, 0.0),
              col="07_Cameras"):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_type = kind
    ob.empty_display_size = size
    link_to(ob, col)
    ob.location = loc
    return ob


def new_camera(name, lens, clip_start=CLIP_START, clip_end=CLIP_END):
    cd = bpy.data.cameras.new(name + "_data")
    cd.lens = float(lens)
    cd.sensor_fit = 'HORIZONTAL'
    cd.sensor_width = 36.0
    cd.clip_start = float(clip_start)
    cd.clip_end = float(clip_end)
    cd.dof.use_dof = False              # 얕은 심도 = 축소 모형 신호. 기본 끔
    cd.display_size = 0.06
    ob = bpy.data.objects.new(name, cd)
    link_to(ob, "07_Cameras")
    return ob


def track_to(cam, target):
    for c in list(cam.constraints):
        cam.constraints.remove(c)
    con = cam.constraints.new('TRACK_TO')
    con.name = "Aim"
    con.target = target
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'
    return con


def new_light(name, kind, energy, color, loc, rot=None, size=None, angle=None,
              soft=None, shadow=True, cone=None, blend=0.5, cutoff=None):
    ld = bpy.data.lights.new(name + "_data", type=kind)
    ld.energy = float(energy)
    ld.color = tuple(color)
    ld.use_shadow = bool(shadow)        # 그림자가 없으면 물체가 공중에 뜬다
    if kind == 'AREA' and size is not None:
        ld.shape = 'SQUARE'
        ld.size = float(size)
    if kind == 'SUN' and angle is not None:
        ld.angle = float(angle)         # 작을수록 또렷한 그림자
    if kind == 'SPOT' and cone is not None:
        ld.spot_size = float(cone)
        ld.spot_blend = float(blend)
    if soft is not None:
        try:
            ld.shadow_soft_size = float(soft)
        except Exception:
            pass
    if cutoff is not None:              # 영향 반경 컷오프 (EEVEE)
        for a, v in (("use_custom_distance", True), ("cutoff_distance", float(cutoff))):
            try:
                setattr(ld, a, v)
            except Exception:
                pass
    ob = bpy.data.objects.new(name, ld)
    link_to(ob, "08_Lights")
    ob.location = loc
    if rot is not None:
        ob.rotation_euler = rot
    return ob


def sun_place(az_deg, el_deg):
    """방위 az / 고도 el 방향'에서' 원점을 비추는 태양의 위치·회전."""
    a, e = math.radians(az_deg), math.radians(el_deg)
    p = (math.cos(e) * math.cos(a) * SUN_DIST,
         math.cos(e) * math.sin(a) * SUN_DIST,
         math.sin(e) * SUN_DIST)
    return p, aim_euler(p, (0.0, 0.0, 0.20))


def lerp3(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


# ==========================================================================
# 5. 빌드 — 선행 조건 확인 + purge
# ==========================================================================
purge("CAM_")
purge("LGT_")
for _cd in [c for c in bpy.data.cameras if c.users == 0]:
    bpy.data.cameras.remove(_cd)
for _ld in [l for l in bpy.data.lights if l.users == 0]:
    bpy.data.lights.remove(_ld)

COL_CAM = link_collection("07_Cameras")
COL_LGT = link_collection("08_Lights")

PATH = bpy.data.objects.get("PATH_Main")
ROOT = bpy.data.objects.get("UGV_Root")
UCAM = bpy.data.objects.get("UGV_Cam")
DRN = bpy.data.objects.get("DRN_Root")
DCAM = bpy.data.objects.get("DRN_Cam")
_missing = [n for n, o in (("PATH_Main", PATH), ("UGV_Root", ROOT), ("UGV_Cam", UCAM),
                           ("DRN_Root", DRN), ("DRN_Cam", DCAM)) if o is None]
if _missing:
    raise RuntimeError(
        "선행 오브젝트 누락: %s\n"
        "70_vehicle(UGV_Root/UGV_Cam) · 75_drone(DRN_Root/DRN_Cam) · "
        "80_motion(PATH_Main) · 82_drone_motion 을 먼저 실행해야 한다.\n"
        "실행 순서: 00→10→20→30→40→50→60→55→70→75→80→82→85→90→95" % ", ".join(_missing))

PATH_LEN = float(PATH.get("length_m", 16.35))
PATH_DUR = float(getattr(PATH.data, "path_duration", TOTAL) or TOTAL)


# ==========================================================================
# 6. CAM_Orbital — 피벗 회전 + Track To
# ==========================================================================
piv = new_empty("CAM_Orbital_Pivot", 'SPHERE', 0.10, (0.0, 0.0, 0.0))
orb_aim = new_empty("CAM_Orbital_Aim", 'PLAIN_AXES', 0.05, (0.0, 0.0, ORBITAL_AIM_Z))
orb_aim.parent = piv                      # 회전축 위라 피벗이 돌아도 제자리
orb_aim.matrix_parent_inverse = mathutils.Matrix.Identity(4)

cam_orb = new_camera("CAM_Orbital", ORBITAL_KEYS[0][6])
cam_orb.parent = piv
cam_orb.matrix_parent_inverse = mathutils.Matrix.Identity(4)
track_to(cam_orb, orb_aim)

_of = [A(k[0]) for k in ORBITAL_KEYS]
for _i in range(1, len(_of)):              # 프레임 중복이면 키가 덮어써진다
    if _of[_i] <= _of[_i - 1]:
        _of[_i] = _of[_i - 1] + 1
bake_channel(piv, "location", 0, _of, [k[1] for k in ORBITAL_KEYS])
bake_channel(piv, "location", 1, _of, [k[2] for k in ORBITAL_KEYS])
bake_channel(piv, "rotation_euler", 2, _of, [math.radians(k[5]) for k in ORBITAL_KEYS])
bake_channel(cam_orb, "location", 0, _of, [k[3] for k in ORBITAL_KEYS])   # 반경
bake_channel(cam_orb, "location", 1, _of, [0.0] * len(_of))
bake_channel(cam_orb, "location", 2, _of, [k[4] for k in ORBITAL_KEYS])   # 높이
bake_channel(cam_orb.data, "lens", None, _of, [k[6] for k in ORBITAL_KEYS])


# ==========================================================================
# 7. CAM_Chase — 경로 지연 추종 리그
# ==========================================================================
# Follow Path 는 curvetime = (eval_time - offset) / path_duration 으로 평가한다.
# offset 단위가 eval_time 단위이므로 지연이 '초'가 아니라 '호장 거리'로 걸린다.
# 저속 코너에서 카메라가 차량을 덮치지 않는다는 점에서 시간 지연보다 낫다.
CHASE_OFFSET = CHASE_LAG_M / max(PATH_LEN, 1e-6) * PATH_DUR

chase_rig = new_empty("CAM_Chase_Rig", 'ARROWS', 0.08, (0.0, 0.0, 0.0))
con = chase_rig.constraints.new('FOLLOW_PATH')
con.name = "Chase_FollowPath"
con.target = PATH
con.use_curve_follow = True        # 리그 +X 가 경로 접선 방향이 된다
con.use_fixed_location = False
con.forward_axis = 'FORWARD_X'
con.up_axis = 'UP_Z'
con.offset = CHASE_OFFSET          # 양수 = 뒤처짐
con.offset_factor = 0.0
con.influence = 1.0

chase_aim = new_empty("CAM_Chase_Aim", 'PLAIN_AXES', 0.03, CHASE_AIM)
chase_aim.parent = ROOT            # 차량 자체를 조준 (리그가 아니라)
chase_aim.matrix_parent_inverse = mathutils.Matrix.Identity(4)

cam_chase = new_camera("CAM_Chase", CHASE_LENS)
cam_chase.parent = chase_rig
cam_chase.matrix_parent_inverse = mathutils.Matrix.Identity(4)
cam_chase.location = (-CHASE_BACK, 0.0, CHASE_UP)
track_to(cam_chase, chase_aim)

# 주의: Track To 는 회전을 통째로 덮어쓴다. rotation_euler 노이즈는 조용히 무시된다.
# 흔들림은 반드시 location(리그 로컬)에 준다 — 위치가 흔들리면 Track To 가 다시
# 조준하므로 결과적으로 화각도 미세하게 흔들린다.
add_noise(flat_fcurve(cam_chase, "location", 1, 0.0),
          CHASE_SHAKE_POS, 5.5, phase=1.7)                       # 좌우
add_noise(flat_fcurve(cam_chase, "location", 2, CHASE_UP),
          CHASE_SHAKE_POS * 0.8, 4.2, phase=5.3)                 # 상하


# ==========================================================================
# 8. CAM_FPV / CAM_Drone — 앵커 부모 고정
# ==========================================================================
# 로컬 변환은 0 으로 둔다. 시점을 바꿔야 하면 카메라가 아니라 앵커(UGV_Cam /
# DRN_Cam)를 옮긴다 (asset-modeler 소관).
cam_fpv = new_camera("CAM_FPV", FPV_LENS, FPV_CLIP_START, FPV_CLIP_END)
cam_fpv.parent = UCAM
cam_fpv.matrix_parent_inverse = mathutils.Matrix.Identity(4)
cam_fpv.location = (0.0, 0.0, 0.0)
cam_fpv.rotation_euler = (0.0, 0.0, 0.0)
if FPV_USE_DOF:
    cam_fpv.data.dof.use_dof = True
    cam_fpv.data.dof.aperture_fstop = FPV_DOF_FSTOP
    cam_fpv.data.dof.focus_distance = FPV_DOF_DISTANCE
for _i, (_s, _sc, _ph) in enumerate(zip(FPV_SHAKE_ROT, (3.2, 4.1, 5.3), (0.0, 3.3, 6.6))):
    add_noise(flat_fcurve(cam_fpv, "rotation_euler", _i, 0.0), _s, _sc, phase=_ph)
add_noise(flat_fcurve(cam_fpv, "location", 1, 0.0), FPV_SHAKE_UP, 2.6, phase=2.2)

# 나디르 드론 시점. DRN_Cam 은 -Z 하방, 화면 위쪽이 기체 전방(+X)이다.
# 로컬 변환 0 이면 카메라 -Z 가 그대로 나디르가 된다. 흔들림은 주지 않는다 —
# 짐벌 안정화된 페이로드 영상이라는 것이 이 컷의 요점이다.
cam_drone = new_camera("CAM_Drone", DRONE_CAM_LENS,
                       DRONE_CAM_CLIP_START, DRONE_CAM_CLIP_END)
cam_drone.parent = DCAM
cam_drone.matrix_parent_inverse = mathutils.Matrix.Identity(4)
cam_drone.location = (0.0, 0.0, 0.0)
cam_drone.rotation_euler = (0.0, 0.0, 0.0)


# ==========================================================================
# 9. CAM_Slowmo / CAM_Avoid / CAM_DroneExt — 고정 리그 (키는 컷 확정 후)
# ==========================================================================
slow_aim = new_empty("CAM_Slowmo_Aim", 'PLAIN_AXES', 0.03, SLOWMO_AIM)
slow_aim.parent = ROOT
slow_aim.matrix_parent_inverse = mathutils.Matrix.Identity(4)

cam_slow = new_camera("CAM_Slowmo", SLOWMO_LENS[0])
cam_slow.location = SLOWMO_POS["ALPHA"]
track_to(cam_slow, slow_aim)      # 고정 위치에서 차량을 팬 추적한다

avoid_aim = new_empty("CAM_Avoid_Aim", 'PLAIN_AXES', 0.03, SLOWMO_AIM)
avoid_aim.parent = ROOT
avoid_aim.matrix_parent_inverse = mathutils.Matrix.Identity(4)

cam_avoid = new_camera("CAM_Avoid", AVOID_POS["GATE"][1][0])
cam_avoid.location = AVOID_POS["GATE"][0]
track_to(cam_avoid, avoid_aim)

dext_aim = new_empty("CAM_DroneExt_Aim", 'PLAIN_AXES', 0.04, (0.0, 0.0, 0.3))
cam_dext = new_camera("CAM_DroneExt", DRONEEXT_SHOTS["TAKEOFF"]["lens"][0][1])
cam_dext.location = DRONEEXT_SHOTS["TAKEOFF"]["pos"][0][1]
track_to(cam_dext, dext_aim)

CAMS = {c.name: c for c in (cam_orb, cam_chase, cam_slow, cam_fpv,
                            cam_avoid, cam_drone, cam_dext)}


# ==========================================================================
# 10. 컷 해석 — 최소 길이 40프레임 강제 + 마커 바인딩
# ==========================================================================
def resolve_at(spec):
    kind = spec[0]
    if kind == "abs":
        return A(int(spec[1]))
    if kind == "cp":
        lead = int(spec[2]) if len(spec) > 2 else -CP_LEAD
        return int(EV.get(spec[1], 1)) + lead
    if kind == "dp":
        off = int(spec[2]) if len(spec) > 2 else 0
        return int(DP.get(spec[1], (1, 1))[0]) + off
    raise ValueError("알 수 없는 컷 앵커: %r" % (spec,))


WARN = []
raw = []
for c in CUT_PLAN:
    d = dict(c)
    d["start"] = max(1, min(resolve_at(c["at"]), TOTAL - MIN_CUT + 1))
    raw.append(d)
raw.sort(key=lambda d: (d["start"], 0 if d["lock"] else 1))
raw[0]["start"] = 1                       # 첫 컷은 반드시 1프레임부터

CUTS = []
for c in raw:
    if CUTS:
        if c["start"] - CUTS[-1]["start"] < MIN_CUT:
            # 유연한 앞 컷을 먼저 버린다. 그래도 안 되면 이 컷을 버린다.
            while (CUTS and not CUTS[-1]["lock"]
                   and c["start"] - CUTS[-1]["start"] < MIN_CUT and len(CUTS) > 1):
                WARN.append("컷 폐기(길이<%d): %s @%d — '%s'"
                            % (MIN_CUT, CUTS[-1]["cam"], CUTS[-1]["start"],
                               CUTS[-1]["label"]))
                CUTS.pop()
            if CUTS and c["start"] - CUTS[-1]["start"] < MIN_CUT:
                WARN.append("컷 폐기(길이<%d): %s @%d — '%s'"
                            % (MIN_CUT, c["cam"], c["start"], c["label"]))
                continue
        if CUTS and CUTS[-1]["cam"] == c["cam"]:
            WARN.append("컷 폐기(직전과 같은 카메라 %s @%d) — '%s'"
                        % (c["cam"], c["start"], c["label"]))
            continue
    CUTS.append(c)

while len(CUTS) > 1 and (TOTAL - CUTS[-1]["start"] + 1) < MIN_CUT:
    WARN.append("마지막 컷 폐기(잔여<%d): %s @%d"
                % (MIN_CUT, CUTS[-1]["cam"], CUTS[-1]["start"]))
    CUTS.pop()

for i, c in enumerate(CUTS):
    c["end"] = (CUTS[i + 1]["start"] - 1) if i + 1 < len(CUTS) else TOTAL
    c["len"] = c["end"] - c["start"] + 1

# --- 마커 바인딩 ---
for m in list(scene.timeline_markers):
    scene.timeline_markers.remove(m)
for i, c in enumerate(CUTS):
    m = scene.timeline_markers.new("CUT_%02d_%s" % (i + 1, c["cam"].replace("CAM_", "")),
                                   frame=c["start"])
    m.camera = CAMS[c["cam"]]
scene.camera = CAMS[CUTS[0]["cam"]]


# ==========================================================================
# 11. 고정 카메라 키 — 컷이 확정된 뒤에 굽는다
# ==========================================================================
def _unpack(ent):
    """테이블 항목을 (위치3, 렌즈2) 로 정규화한다.

    SLOWMO_POS 는 (x, y, z) 만 담고 렌즈는 SLOWMO_LENS 공통,
    AVOID_POS 는 ((x, y, z), (lens0, lens1)) 로 컷마다 렌즈가 다르다.
    """
    if isinstance(ent[0], (tuple, list)):
        return tuple(ent[0]), tuple(ent[1])
    return tuple(ent), tuple(SLOWMO_LENS)


def fixed_cam_keys(cam, cuts, table):
    """컷별 고정 위치 + 렌즈 푸시인. 위치는 컷 시작 2프레임 전 CONSTANT 로 순간이동."""
    if not cuts:
        return 0
    pf, px, py, pz = [1], [], [], []
    first, _ = _unpack(table[cuts[0]["aim"]])
    px.append(first[0]); py.append(first[1]); pz.append(first[2])
    lf, lv = [], []
    for c in cuts:
        pos, lens = _unpack(table[c["aim"]])
        f = max(2, c["start"] - 2)
        if f <= pf[-1]:
            f = pf[-1] + 1
        pf.append(f); px.append(pos[0]); py.append(pos[1]); pz.append(pos[2])
        for ff, vv in ((c["start"], lens[0]), (c["end"], lens[1])):
            if lf and ff <= lf[-1]:
                ff = lf[-1] + 1
            lf.append(int(ff)); lv.append(float(vv))
    # CONSTANT: 컷 직전에 순간이동하고 컷 내내 고정된다
    for idx, arr in ((0, px), (1, py), (2, pz)):
        bake_channel(cam, "location", idx, pf, arr, interp='CONSTANT', handle='VECTOR')
    bake_channel(cam.data, "lens", None, lf, lv, interp='LINEAR', handle='VECTOR')
    return len(cuts)


SM = [c for c in CUTS if c["cam"] == "CAM_Slowmo"]
AVC = [c for c in CUTS if c["cam"] == "CAM_Avoid"]
n_slow = fixed_cam_keys(cam_slow, SM, SLOWMO_POS)
n_avoid = fixed_cam_keys(cam_avoid, AVC, AVOID_POS)

# --- CAM_DroneExt: 컷 안에서는 크레인/달리, 컷 사이는 CONSTANT 순간이동 -----
DEX = [c for c in CUTS if c["cam"] == "CAM_DroneExt"]
dex_report = []
if DEX:
    pos_seg = [[], [], []]
    lens_seg, aim_seg = [], [[], [], []]
    for c in DEX:
        sh = DRONEEXT_SHOTS[c["shot"]]
        s, e = c["start"], c["end"]
        span = max(1, e - s)
        # 위치
        keys = [(s + int(round(t * span)), p) for t, p in sh["pos"]]
        for ax in range(3):
            pos_seg[ax].append([(f, p[ax]) for f, p in keys])
        # 렌즈
        lens_seg.append([(s + int(round(t * span)), v) for t, v in sh["lens"]])
        # 조준점
        if sh["aim"] == "drone":
            n = int(sh.get("aim_samples", 7))
            frames = [s + int(round(i * span / float(n - 1))) for i in range(n)]
            b = sh.get("aim_bias", (0.0, 0.0, 0.0))
            zf = float(sh.get("aim_follow", 1.0))
            pts, zmeas = [], []
            for f in frames:
                scene.frame_set(f)
                bpy.context.view_layer.update()
                w = DRN.matrix_world.translation
                zmeas.append(w.z)
                pts.append((f, (w.x + b[0], w.y + b[1], w.z * zf + b[2])))
            dex_report.append("%s: DRN_Root 실측 추적 %d샘플 (드론 z %.3f→%.3f, "
                              "조준 추종 %.0f%%)"
                              % (c["shot"], n, zmeas[0], zmeas[-1], zf * 100))
        else:
            p = sh["aim_pos"]
            pts = [(s, p), (e, p)]
            dex_report.append("%s: 고정 조준 (%.2f, %.2f, %.2f)" % ((c["shot"],) + tuple(p)))
        for ax in range(3):
            aim_seg[ax].append([(f, p[ax]) for f, p in pts])
    for ax in range(3):
        bake_segments(cam_dext, "location", ax, pos_seg[ax])
        bake_segments(dext_aim, "location", ax, aim_seg[ax])
    bake_segments(cam_dext.data, "lens", None, lens_seg)
    scene.frame_set(1)


# ==========================================================================
# 12. 라이팅 — 3점 + 림 2개 + 화재 2개 + QR + 월드
# ==========================================================================
# 균일한 조명은 형태를 납작하게 만든다. 대비를 세게 준다.
lgt_key = new_light("LGT_Key", 'AREA', KEY_POWER, KEY_COLOR, KEY_POS,
                    rot=aim_euler(KEY_POS, KEY_AIM), size=KEY_SIZE)
lgt_fill = new_light("LGT_Fill", 'AREA', FILL_POWER, FILL_COLOR, FILL_POS,
                     rot=aim_euler(FILL_POS, FILL_AIM), size=FILL_SIZE)

# 림 라이트가 스카이라인을 만든다. 건물 윤곽의 밝은 테두리가 오비탈 샷 인상의 절반이다.
# 하나만 두면 카메라가 도는 동안 역광이 순광으로 바뀌어 윤곽이 사라진다.
_p, _r = sun_place(RIM_A["az"], RIM_A["el"])
lgt_rim_a = new_light("LGT_Rim_A", 'SUN', RIM_A["energy"], RIM_A["color"], _p,
                      rot=_r, angle=RIM_A["angle"])
_p, _r = sun_place(RIM_B["az"], RIM_B["el"])
lgt_rim_b = new_light("LGT_Rim_B", 'SUN', RIM_B["energy"], RIM_B["color"], _p,
                      rot=_r, angle=RIM_B["angle"])

LIGHTS = [lgt_key, lgt_fill, lgt_rim_a, lgt_rim_b]

# --- 화재 반사광 ----------------------------------------------------------
fire_lines = []
if FIRE_LIGHT:
    _fspec = SPEC.get("fire_buildings", [])
    if not _fspec:
        _fspec = [{"sector": 2, "intensity": 1.0}, {"sector": 9, "intensity": 0.85}]
        WARN.append("SPEC.fire_buildings 없음 — 섹터 2/9 기본값으로 화재광을 배치했다")
    for _i, fb in enumerate(_fspec):
        n = int(fb["sector"])
        inten = float(fb.get("intensity", 1.0))
        sec = SPEC["sectors"].get(str(n))
        if sec is None:
            WARN.append("섹터 %d 스펙 없음 — 화재광 생략" % n)
            continue
        cx, cy = sec["pos"][0], sec["pos"][1]
        cz = float(sec["h"]) + FIRE_Z_OVER_ROOF
        e = FIRE_POWER * inten
        lf = new_light("LGT_Fire_%02d" % n, 'POINT', e, FIRE_COLOR, (cx, cy, cz),
                       soft=FIRE_SOFT, shadow=True, cutoff=FIRE_CUTOFF)
        # 깜박임 — 고정값 F커브에 노이즈를 얹는다. 위상을 어긋내 두 동이 동기화되지 않게.
        add_noise(flat_fcurve(lf.data, "energy", None, e),
                  e * FIRE_FLICKER, FIRE_FLICKER_SCALE, phase=3.7 * (_i + 1))
        LIGHTS.append(lf)
        fire_lines.append("LGT_Fire_%02d (%.2f, %.2f, %.2f) %.2f W x%.2f 깜박임 ±%.0f%%"
                          % (n, cx, cy, cz, e, inten, FIRE_FLICKER * 100))
# 40_sectors 가 만든 자기조명(SEC_*_Fire_Light)은 접두사가 달라 purge 되지 않는다.
_sec_fire = [o for o in bpy.data.objects
             if o.type == 'LIGHT' and o.name.startswith("SEC_") and "Fire_Light" in o.name]

# --- QR 아군표식 ----------------------------------------------------------
qr_lines = []
QRM = bpy.data.objects.get("QRM_01")


def qr_materials():
    """QRM_01(과 그 부품)에 실제로 할당된 QR_MAT_* 를 찾는다. 없으면 이름으로 폴백."""
    found = []
    if QRM is not None:
        for ob in [QRM] + list(QRM.children_recursive):
            for slot in getattr(ob, "material_slots", []):
                m = slot.material
                if m is not None and m.name.startswith("QR_MAT"):
                    found.append(m)
    if not found:
        found = [m for m in bpy.data.materials if m.name.startswith("QR_MAT")]
    out, seen = [], set()
    for m in found:
        if m.name not in seen:
            seen.add(m.name)
            out.append(m)
    return out


for _m in qr_materials():
    _m.use_nodes = True
    nt = _m.node_tree
    if nt is None:
        WARN.append("%s 에 노드 트리가 없다 — 이미시브 부스트 생략" % _m.name)
        continue
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    tex = next((n for n in nt.nodes if n.type == 'TEX_IMAGE'), None)
    if bsdf is None:
        WARN.append("%s 에 Principled 노드가 없다 — 이미시브 부스트 생략" % _m.name)
        continue
    ekey = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
    if tex is not None and ekey in bsdf.inputs:
        # 텍스처를 그대로 이미시브에 물린다 → 흰 모듈만 뜨고 검은 모듈은 0 으로 남는다.
        # links.new 는 이미 연결된 입력을 교체하므로 재실행해도 중복되지 않는다.
        nt.links.new(tex.outputs["Color"], bsdf.inputs[ekey])
    elif ekey in bsdf.inputs:
        bsdf.inputs[ekey].default_value = (1.0, 1.0, 1.0, 1.0)
    if "Emission Strength" in bsdf.inputs:
        bsdf.inputs["Emission Strength"].default_value = QR_EMISSION
    qr_lines.append("%s 이미시브 %.2f (텍스처 Color → %s)"
                    % (_m.name, QR_EMISSION, ekey if tex is not None else "흰색 상수"))

lgt_qr = None
if QR_FILL and QRM is not None:
    # 판 법선(로컬 +X)의 월드 방향과 판 중심을 오브젝트에서 직접 읽는다.
    _n3 = (QRM.matrix_world.to_3x3() @ mathutils.Vector((1.0, 0.0, 0.0)))
    _n3.z = 0.0
    _n3.normalize()
    _bw = float(SPEC.get("markers", {}).get("size", 0.05))
    _cs = [QRM.matrix_world @ mathutils.Vector(c) for c in QRM.bound_box] \
        if QRM.type == 'MESH' else []
    if _cs:
        _cx = sum(v.x for v in _cs) / len(_cs)
        _cy = sum(v.y for v in _cs) / len(_cs)
        _cz = max(v.z for v in _cs) - _bw * 0.5
    else:
        _cx, _cy = QRM.matrix_world.translation.x, QRM.matrix_world.translation.y
        _cz = 0.014 + _bw * 0.5
    plate = (_cx, _cy, _cz)
    lpos = (_cx + _n3.x * QR_FILL_DIST, _cy + _n3.y * QR_FILL_DIST, _cz + QR_FILL_UP)
    lgt_qr = new_light("LGT_QR_Fill", 'SPOT', QR_FILL_POWER, QR_FILL_COLOR, lpos,
                       rot=aim_euler(lpos, plate), soft=0.02, shadow=False,
                       cone=QR_FILL_CONE, blend=0.55, cutoff=0.9)
    LIGHTS.append(lgt_qr)
    qr_lines.append("LGT_QR_Fill SPOT %.1f W, 판 중심(%.2f, %.2f, %.3f) 정면 %.2f m "
                    "/ 콘 %.0f° / 그림자 OFF"
                    % (QR_FILL_POWER, plate[0], plate[1], plate[2], QR_FILL_DIST,
                       math.degrees(QR_FILL_CONE)))
elif QR_FILL:
    WARN.append("QRM_01 이 없다 — LGT_QR_Fill 생략 (55_placement 실행 여부 확인)")

# --- 월드 (오브젝트가 아니라 ID 블록. purge 대상이 아니므로 이름으로 재사용) ---
world = bpy.data.worlds.get("MAICON_World")
if world is None:
    world = bpy.data.worlds.new("MAICON_World")
world.use_nodes = True
scene.world = world
_bg = next((nd for nd in world.node_tree.nodes if nd.type == 'BACKGROUND'), None)
if _bg is None:
    _bg = world.node_tree.nodes.new('ShaderNodeBackground')
    _out = next((nd for nd in world.node_tree.nodes if nd.type == 'OUTPUT_WORLD'), None)
    if _out is None:
        _out = world.node_tree.nodes.new('ShaderNodeOutputWorld')
    world.node_tree.links.new(_bg.outputs["Background"], _out.inputs["Surface"])
_bg.inputs["Color"].default_value = rgba(WORLD_COLOR)
_bg.inputs["Strength"].default_value = WORLD_STRENGTH
world.color = tuple(WORLD_COLOR)


# ==========================================================================
# 13. QA — 카메라가 실제로 무엇을 보는지 실측
# ==========================================================================
# 카메라 오브젝트가 존재한다는 사실만으로는 아무것도 보증하지 못한다.
# 컷마다 프레임을 실제로 평가해 (a) 지오메트리 관통 (b) 피사체 화면 내 위치를 잰다.
try:
    from bpy_extras.object_utils import world_to_camera_view as _w2c
except Exception:
    _w2c = None

# 정적 오브젝트의 월드 AABB (애니메이션이 없으므로 한 번만 계산한다)
_QA_PREFIX = ("SEC_", "OBJ_", "ARU_", "QRM_", "HZD_")
_QA_SKIP = ("_Smoke",)
STATIC_BOXES = []
for _o in bpy.data.objects:
    if _o.type != 'MESH' or not _o.name.startswith(_QA_PREFIX):
        continue
    if any(s in _o.name for s in _QA_SKIP):
        continue
    _cs = [_o.matrix_world @ mathutils.Vector(c) for c in _o.bound_box]
    _lo = (min(v.x for v in _cs), min(v.y for v in _cs), min(v.z for v in _cs))
    _hi = (max(v.x for v in _cs), max(v.y for v in _cs), max(v.z for v in _cs))
    # 노면 데칼(포트홀·균열 같은 z<2 cm 납작한 것)은 제외한다. 카메라가 0.06 m
    # 높이로 그 위를 지날 때마다 가짜 관통 경고가 뜬다 — 실제로는 통과하지 않는다.
    if _hi[2] < 0.02:
        continue
    STATIC_BOXES.append((_o.name, _lo, _hi))


def clearance(cam):
    """카메라와 정적 지오메트리 AABB 사이 최소 3D 거리. 박스 내부면 0."""
    w = cam.matrix_world.translation
    best, who = 1e9, "-"
    for name, lo, hi in STATIC_BOXES:
        dx = max(lo[0] - w.x, 0.0, w.x - hi[0])
        dy = max(lo[1] - w.y, 0.0, w.y - hi[1])
        dz = max(lo[2] - w.z, 0.0, w.z - hi[2])
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        if d < best:
            best, who = d, name
    return best, who


def in_frame(cam, target):
    if _w2c is None or target is None:
        return None
    uv = _w2c(scene, cam, target)
    return (uv.x, uv.y, uv.z)


FIRE_PT = {}
for _n in (2, 9):
    _s = SPEC["sectors"].get(str(_n))
    if _s:
        FIRE_PT[_n] = mathutils.Vector((_s["pos"][0], _s["pos"][1],
                                        float(_s["h"]) + 0.04))

if QA_STRIDE:
    for c in CUTS:
        cam = CAMS[c["cam"]]
        worst_d, worst_who, worst_f = 1e9, "-", c["start"]
        stat = {"ugv": [0, 0], "drn": [0, 0], "f2": [0, 0], "f9": [0, 0]}
        fr = list(range(c["start"], c["end"] + 1, QA_STRIDE))
        if fr[-1] != c["end"]:
            fr.append(c["end"])
        for f in fr:
            scene.frame_set(f)
            bpy.context.view_layer.update()
            d, who = clearance(cam)
            if d < worst_d:
                worst_d, worst_who, worst_f = d, who, f
            for key, tgt in (("ugv", ROOT.matrix_world.translation),
                             ("drn", DRN.matrix_world.translation),
                             ("f2", FIRE_PT.get(2)), ("f9", FIRE_PT.get(9))):
                if tgt is None:
                    continue
                uv = in_frame(cam, tgt)
                if uv is None:
                    continue
                stat[key][1] += 1
                if uv[2] > 0.0 and 0.0 <= uv[0] <= 1.0 and 0.0 <= uv[1] <= 1.0:
                    stat[key][0] += 1
        c["qa"] = dict(clear=worst_d, who=worst_who, at=worst_f, stat=stat,
                       n=len(fr))

scene.frame_set(1)


# ==========================================================================
# 14. 리포트
# ==========================================================================
def seg_at(f):
    for nm, a, b in SEG:
        if a <= f <= b:
            return nm
    return "-"


def dphase_at(f):
    for nm, (a, b) in DP.items():
        if a <= f <= b:
            return nm
    return "-"


print("[90_camera] ================= 컷 시트 (%d컷 / 최소 %d프레임) ================="
      % (len(CUTS), MIN_CUT))
for i, c in enumerate(CUTS):
    q = c.get("qa", {})
    print("  %02d  f%3d-%3d (%3d f / %4.1f s)  %-8s  [UGV %s | DRN %s]"
          % (i + 1, c["start"], c["end"], c["len"], c["len"] / float(FPS),
             c["cam"].replace("CAM_", ""),
             seg_at((c["start"] + c["end"]) // 2),
             dphase_at((c["start"] + c["end"]) // 2)))
    print("        %s" % c["label"])
    if q:
        st = q["stat"]
        vis = " ".join("%s %d/%d" % (k.upper(), v[0], v[1])
                       for k, v in (("ugv", st["ugv"]), ("drn", st["drn"]),
                                    ("f2", st["f2"]), ("f9", st["f9"])) if v[0])
        print("        여유 %.3f m (%s@f%d) | 화면내 %s"
              % (q["clear"], q["who"], q["at"], vis if vis else "(피사체 없음)"))

print("[90_camera] --- 체크포인트 대조 (리드 +%d) ---" % CP_LEAD)
for nm in ("ALPHA", "BRAVO", "CHARLIE", "FINISH"):
    f = EV[nm]
    o = next((c for c in CUTS if c["start"] <= f <= c["end"]), None)
    print("  %-8s 통과 f%3d  ->  %-9s 컷 f%d~%d (리드 %+d)"
          % (nm, f, o["cam"].replace("CAM_", "") if o else "미커버",
             o["start"] if o else -1, o["end"] if o else -1,
             (f - o["start"]) if o else 0))

print("[90_camera] --- 회피 이벤트 커버리지 ---")
for nm in ("pothole_1", "barrier_1", "pothole_2", "barrier_2"):
    if nm not in AV:
        continue
    a, apex, b = AV[nm]
    o = next((c for c in CUTS if c["start"] <= apex <= c["end"]), None)
    dip = AVX.get(nm, {}).get("speed_dip_pct")
    print("  %-10s f%3d~%3d 정점 f%3d (딥 %s)  ->  %s"
          % (nm, a, b, apex, ("%.0f%%" % dip) if dip is not None else "-",
             ("%s 컷 f%d~%d" % (o["cam"].replace("CAM_", ""), o["start"], o["end"]))
             if o else "미커버"))

print("[90_camera] --- 드론 구간 커버리지 ---")
for nm in ("TAKEOFF", "SHOOT_2", "SHOOT_9", "LAND"):
    a, b = DP[nm]
    mid = (a + b) // 2
    o = next((c for c in CUTS if c["start"] <= mid <= c["end"]), None)
    print("  %-8s f%3d~%3d  ->  %s"
          % (nm, a, b, ("%s 컷 f%d~%d" % (o["cam"].replace("CAM_", ""),
                                          o["start"], o["end"])) if o else "미커버"))

print("[90_camera] --- 리그 ---")
print("  Orbital   키 %d개 / 렌즈 %.0f~%.0fmm / 높이 %.2f~%.2f m / 반경 %.2f~%.2f m"
      % (len(ORBITAL_KEYS),
         min(k[6] for k in ORBITAL_KEYS), max(k[6] for k in ORBITAL_KEYS),
         min(k[4] for k in ORBITAL_KEYS), max(k[4] for k in ORBITAL_KEYS),
         min(k[3] for k in ORBITAL_KEYS), max(k[3] for k in ORBITAL_KEYS)))
print("  Chase     PATH_Main 지연추종 offset=%.2f (호장 %.2f m / 경로 %.2f m, dur %.0f)"
      " 로컬(-%.2f, 0, %.2f) %.0fmm"
      % (CHASE_OFFSET, CHASE_LAG_M, PATH_LEN, PATH_DUR, CHASE_BACK, CHASE_UP, CHASE_LENS))
print("  Slowmo    고정 %d컷 CONSTANT + Track To(UGV) / 렌즈 %.0f→%.0fmm"
      % (n_slow, SLOWMO_LENS[0], SLOWMO_LENS[1]))
print("  Avoid     고정 %d컷 CONSTANT + Track To(UGV) / GATE %.0f→%.0f, POTHOLE2 %.0f→%.0fmm"
      % (n_avoid, AVOID_POS["GATE"][1][0], AVOID_POS["GATE"][1][1],
         AVOID_POS["POTHOLE2"][1][0], AVOID_POS["POTHOLE2"][1][1]))
print("  FPV       부모=UGV_Cam(짐벌 고정) / %.0fmm / clip_start %.4f / DOF %s"
      % (FPV_LENS, FPV_CLIP_START, "ON f/%.0f" % FPV_DOF_FSTOP if FPV_USE_DOF else "OFF"))
print("  Drone     부모=DRN_Cam(나디르 -Z) / %.0fmm / clip_start %.4f / 흔들림 없음"
      % (DRONE_CAM_LENS, DRONE_CAM_CLIP_START))
print("  DroneExt  %d컷 (%s)" % (len(DEX), " | ".join(dex_report) if dex_report else "-"))
print("  라이팅    Key %.0fW(%.1fm) / Fill %.0fW(%.1fm) / Rim %.1f+%.1f(SUN) / 월드 %.3f"
      % (KEY_POWER, KEY_SIZE, FILL_POWER, FILL_SIZE,
         RIM_A["energy"], RIM_B["energy"], WORLD_COLOR[2] * WORLD_STRENGTH))
for line in fire_lines:
    print("  화재광    %s" % line)
if _sec_fire:
    print("  화재광    (+ 40_sectors 자기조명 %s — 접두사가 달라 합산된다)"
          % ", ".join("%s %.1fW" % (o.name, o.data.energy) for o in _sec_fire))
for line in qr_lines:
    print("  QR        %s" % line)

_bad = [c for c in CUTS if c["len"] < MIN_CUT]
_pen = [c for c in CUTS if c.get("qa", {}).get("clear", 9.0) < QA_CLEAR_WARN]
_nocp = [n for n in ("ALPHA", "BRAVO", "CHARLIE")
         if not any(c["start"] <= EV[n] <= c["end"] for c in CUTS)]
for w in WARN:
    print("  [경고] " + w)
for c in _bad:
    print("  [경고] 컷 길이 %d < %d — %s @f%d" % (c["len"], MIN_CUT, c["cam"], c["start"]))
for c in _pen:
    print("  [경고] 카메라-지오메트리 근접 %.3f m (%s) — %s @f%d"
          % (c["qa"]["clear"], c["qa"]["who"], c["cam"], c["qa"]["at"]))
for n in _nocp:
    print("  [경고] 체크포인트 %s 가 어느 컷에도 안 들어왔다" % n)
if TL is None:
    print("  [경고] timeline.json 이 없어 인계 프레임으로 컷을 잡았다. **타이밍 미확정**")
if DTL is None:
    print("  [경고] drone_timeline.json 이 없어 드론 구간을 인계값으로 잡았다")

print("[90_camera] cameras=%d lights=%d cuts=%d markers=%d | frames 1-%d @%dfps | %s"
      % (len(CAMS), len(LIGHTS), len(CUTS), len(scene.timeline_markers), TOTAL, FPS,
         "measured" if (TL is not None and DTL is not None) else "PARTIAL-ESTIMATE"))
