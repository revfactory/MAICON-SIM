# -*- coding: utf-8 -*-
"""
95_render.py — 렌더 설정 (cinematographer 산출)

★ 이 스크립트는 **설정만** 한다. bpy.ops.render.render() 를 호출하지 않는다. ★

전체 애니메이션 렌더는 Blender 를 수 분~수십 분 블로킹하고 그동안 MCP 가 응답하지
않는다. 잘못된 룩으로 30분을 태우지 않으려면 순서를 지킨다:

    1) exec(open(".../95_render.py").read())      <- 설정 적용 (이 파일)
    2) render_still(150)                          <- 단일 프레임 테스트. 룩 확인
    3) 사용자 확인                                 <- 예상 소요를 알리고 승인받는다
    4) render_animation()                         <- 전체 렌더

2/4 단계는 오케스트레이터가 **명시적으로 호출**해야 실행된다. 로드만으로는 안 돈다.

--------------------------------------------------------------------------
purge 가 없는 이유
--------------------------------------------------------------------------
이 스크립트는 오브젝트를 하나도 만들지 않는다. 씬 설정 프로퍼티만 덮어쓰므로
몇 번을 다시 실행해도 결과가 같다(멱등). 지울 접두사가 없다.
"""

import bpy
import json
import math
import os

WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
exec(open(os.path.join(WORKSPACE, "scripts", "00_common.py")).read())

scene = bpy.context.scene


# ==========================================================================
# 1. 프레임 상수 — >>> 실측 갱신 지점 <<< (90_camera.py 와 동일 규칙)
# ==========================================================================
TIMELINE_PATH = os.path.join(WORKSPACE, "spec", "timeline.json")
FALLBACK = {"fps": 30, "total_frames": 720}     # motion-director 인계: 600 아님

TL = None
if os.path.exists(TIMELINE_PATH):
    try:
        with open(TIMELINE_PATH, "r", encoding="utf-8") as _fp:
            TL = json.load(_fp)
    except Exception as e:
        print("  [경고] timeline.json 파싱 실패 (%s) — 추정값으로 진행" % e)

FPS = int(TL.get("fps", FALLBACK["fps"])) if TL else FALLBACK["fps"]
TOTAL = int(TL.get("total_frames", FALLBACK["total_frames"])) if TL else FALLBACK["total_frames"]
TIMELINE_SOURCE = "measured" if TL else "ESTIMATED (timeline.json 없음)"

# 모션 블러: motion-director 필수 인계 사항.
# 최고속에서 바퀴가 프레임당 0.26회전하고 트레드 러그가 14개라, 블러가 없으면
# 바퀴가 거꾸로 도는 스트로브(웨건휠)가 보인다.
MB_SHUTTER = 0.5
MB_STEPS = 4
if TL and isinstance(TL.get("render_hint"), dict):
    MB_SHUTTER = float(TL["render_hint"].get("shutter", MB_SHUTTER))


# ==========================================================================
# 2. 출력 파라미터
# ==========================================================================
RES_X, RES_Y = 1920, 1080
SAMPLES = 64            # 차선 폭 15 mm. 32 미만이면 계단 현상이 심하다
OUT_MP4 = os.path.join(OUTPUT_DIR, "maicon_demo.mp4")

PREVIEW_PERCENT, PREVIEW_SAMPLES = 50, 8
STILL_FRAME = 150


def _try(owner, attr, value):
    """버전마다 있고 없는 프로퍼티를 안전하게 설정. 설정됐으면 True."""
    if owner is None or not hasattr(owner, attr):
        return False
    try:
        setattr(owner, attr, value)
        return True
    except Exception:
        return False


# ==========================================================================
# 3. 엔진 — EEVEE
# ==========================================================================
# Cycles 는 이 씬에서 프레임당 수십 초가 걸려 720프레임이 몇 시간이 된다.
# 데모 영상의 룩은 EEVEE 로 충분하다. 엔진 이름은 버전마다 다르므로 분기한다.
_ENGINES = [i.identifier for i in
            bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
if 'BLENDER_EEVEE_NEXT' in _ENGINES:
    ENGINE = 'BLENDER_EEVEE_NEXT'          # 4.2 ~ 5.1
elif 'BLENDER_EEVEE' in _ENGINES:
    ENGINE = 'BLENDER_EEVEE'               # 4.1 이하, 그리고 5.2+ (아래 주석 참조)
else:
    ENGINE = _ENGINES[0]
scene.render.engine = ENGINE

# 엔진 '이름'으로 세대를 판별하면 안 된다.
# 5.2 는 EEVEE Next 를 옛 이름 'BLENDER_EEVEE' 로 통합했다. 이름으로 분기하면
# 5.2 에서 구형 경로(use_gtao / use_ssr / use_bloom)를 타는데 그 프로퍼티들이
# 전부 존재하지 않아 _try 가 조용히 실패하고 **AO 가 통째로 꺼진다**.
# AO 가 없으면 물체가 접지되어 보이지 않고, 축소 모형에서 그 효과가 특히 크다.
# 그래서 이름이 아니라 프로퍼티 존재 여부로 세대를 판별한다.
EEVEE_NEXT = hasattr(scene.eevee, "use_raytracing")     # 4.2+ / 5.x
EEVEE_LEGACY = hasattr(scene.eevee, "use_gtao")         # 4.1 이하
EEVEE_GEN = "Next" if EEVEE_NEXT else ("Legacy" if EEVEE_LEGACY else "unknown")


# ==========================================================================
# 4. 공통 설정
# ==========================================================================
def apply_common():
    r = scene.render
    r.resolution_x, r.resolution_y = RES_X, RES_Y
    r.resolution_percentage = 100
    r.fps = FPS
    r.fps_base = 1.0
    r.filter_size = 1.5
    r.film_transparent = False
    _try(r, "use_persistent_data", True)     # 프레임 간 데이터 재사용 — 애니 렌더가 빨라진다
    scene.frame_start = 1
    scene.frame_end = TOTAL
    scene.frame_step = 1

    # --- 모션 블러 (4.2 는 render, 그 이전은 eevee 밑에 있다. 둘 다 시도) ---
    ok = _try(r, "use_motion_blur", True)
    _try(r, "motion_blur_shutter", MB_SHUTTER)
    _try(r, "motion_blur_position", 'CENTER')
    _try(r, "motion_blur_steps", MB_STEPS)
    ok2 = _try(scene.eevee, "use_motion_blur", True)
    _try(scene.eevee, "motion_blur_shutter", MB_SHUTTER)
    _try(scene.eevee, "motion_blur_steps", MB_STEPS)
    _try(scene.eevee, "motion_blur_position", 'CENTER')
    if not (ok or ok2):
        print("  [경고] 모션 블러 프로퍼티를 찾지 못했다 — 바퀴 스트로브가 보일 수 있다")

    # --- 그림자 (없으면 물체가 공중에 뜬 것처럼 보인다) ---
    _try(scene.eevee, "use_shadows", True)              # 4.2+
    _try(scene.eevee, "use_soft_shadows", True)         # 4.1 이하
    _try(scene.eevee, "shadow_cube_size", '2048')
    _try(scene.eevee, "shadow_cascade_size", '4096')
    _try(scene.eevee, "shadow_ray_count", 2)            # 4.2+
    _try(scene.eevee, "shadow_step_count", 6)
    _try(scene.eevee, "shadow_resolution_scale", 1.0)
    _try(scene.eevee, "use_shadow_jitter_viewport", True)

    # --- AO / 반사 ---
    if EEVEE_NEXT:
        _try(scene.eevee, "use_raytracing", True)
        _try(scene.eevee, "ray_tracing_method", 'SCREEN')
        rt = getattr(scene.eevee, "ray_tracing_options", None)
        _try(rt, "use_denoise", True)
        _try(rt, "resolution_scale", '2')
        _try(rt, "screen_trace_quality", 0.25)
        _try(scene.eevee, "fast_gi_method", 'AMBIENT_OCCLUSION_ONLY')
        _try(scene.eevee, "fast_gi_distance", 0.10)     # 축소 스케일에 맞춘 짧은 거리
        _try(scene.eevee, "use_overscan", True)
        _try(scene.eevee, "overscan_size", 3.0)
    elif EEVEE_LEGACY:
        _try(scene.eevee, "use_gtao", True)
        _try(scene.eevee, "gtao_distance", 0.08)        # 기본 0.2 m 는 차량(0.13 m)보다 크다
        _try(scene.eevee, "gtao_factor", 1.0)
        _try(scene.eevee, "use_ssr", True)
        _try(scene.eevee, "use_ssr_halfres", False)
        _try(scene.eevee, "use_bloom", True)            # 4.2 에서 제거(컴포지터 Glare 로 이동)
        _try(scene.eevee, "bloom_intensity", 0.020)
        _try(scene.eevee, "bloom_threshold", 1.2)
    else:
        print("  [경고] EEVEE 세대를 판별하지 못했다 — AO/반사가 꺼진 채 렌더된다. "
              "물체가 공중에 뜬 것처럼 보이면 이 경고가 원인이다")
    _try(scene.eevee, "use_volumetric_lights", False)

    # --- 컬러 매니지먼트 ---
    vs = scene.view_settings
    for tf in ('AgX', 'Filmic', 'Standard'):
        if _try(vs, "view_transform", tf):
            break
    for lk in ('AgX - Punchy', 'Punchy', 'Medium High Contrast', 'None'):
        if _try(vs, "look", lk):
            break
    vs.exposure = 0.0        # 어두우면 LGT_Key 와 월드를 먼저 올린다. 노출은 마지막 수단
    vs.gamma = 1.0
    _try(scene.display_settings, "display_device", 'sRGB')


def set_media(kind):
    """출력 미디어 종류를 **명시적으로** 전환한다.

    Blender 5.x 는 image_settings.media_type('IMAGE'/'MULTI_LAYER_IMAGE'/'VIDEO')
    이 생겼고, media_type='VIDEO' 를 **먼저** 넣어야 file_format 에 'FFMPEG' 이
    나타난다. IMAGE 모드에서 FFMPEG 을 대입하면 enum not found 로 죽는다.
    반대로 비디오 모드인 채 스틸을 뽑으면 엉뚱한 출력이 나오므로,
    스틸/애니메이션을 오갈 때마다 매번 이 함수로 모드를 선언한다.
    구버전에는 media_type 이 없으므로 hasattr 로 건너뛴다.

        kind: 'VIDEO' -> FFMPEG,  'IMAGE' -> PNG
    """
    ims = scene.render.image_settings
    if kind == 'VIDEO':
        _try(ims, "media_type", 'VIDEO')        # 5.x. 이 줄이 반드시 먼저다
        ims.file_format = 'FFMPEG'
    else:
        _try(ims, "media_type", 'IMAGE')
        ims.file_format = 'PNG'
    _try(ims, "color_mode", 'RGB')              # file_format 확정 후에 넣는다
    return ims


def apply_output(path=OUT_MP4):
    r = scene.render
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    set_media('VIDEO')
    ff = r.ffmpeg
    ff.format = 'MPEG4'
    ff.codec = 'H264'
    ff.constant_rate_factor = 'HIGH'
    ff.ffmpeg_preset = 'GOOD'
    _try(ff, "gopsize", 18)
    _try(ff, "use_max_b_frames", False)
    ff.audio_codec = 'NONE'
    # 경로가 이미 .mp4 로 끝나면 Blender 는 프레임 범위를 덧붙이지 않는다.
    r.use_file_extension = True
    r.use_overwrite = True
    r.filepath = path


def apply_final():
    """최종 품질. 이 파일을 로드하면 자동으로 이 상태가 된다."""
    apply_common()
    scene.render.resolution_percentage = 100
    _try(scene.eevee, "taa_render_samples", SAMPLES)
    apply_output(OUT_MP4)


def apply_preview(percent=PREVIEW_PERCENT, samples=PREVIEW_SAMPLES,
                  path=None):
    """저품질 빠른 프리뷰. '렌더가 느리다' 는 피드백에 먼저 쓴다."""
    apply_common()
    scene.render.resolution_percentage = int(percent)
    _try(scene.eevee, "taa_render_samples", int(samples))
    apply_output(path or os.path.join(OUTPUT_DIR, "maicon_demo_preview.mp4"))
    print("[95_render] 프리뷰 모드: %d%% / 샘플 %d" % (percent, samples))


# ==========================================================================
# 5. 실행 함수 — 정의만 한다. 여기서 호출하지 않는다.
# ==========================================================================
def render_still(frame=STILL_FRAME, name=None, samples=None):
    """단일 프레임 테스트 렌더. **전체 렌더 전에 반드시 이것부터 돌린다.**

    output/stills/ 에 PNG 로 떨구고 원래의 mp4 출력 설정을 복원한다.
    마커 바인딩 덕분에 해당 프레임의 컷 카메라가 자동으로 선택된다.
    """
    r = scene.render
    ims = r.image_settings
    keep = (r.filepath, getattr(ims, "media_type", None), ims.file_format,
            ims.color_mode, getattr(scene.eevee, "taa_render_samples", SAMPLES))
    try:
        scene.frame_set(int(frame))
        cam = scene.camera
        out = name or "still_f%04d_%s.png" % (
            int(frame), (cam.name.replace("CAM_", "") if cam else "nocam"))
        if not os.path.isdir(STILLS_DIR):
            os.makedirs(STILLS_DIR, exist_ok=True)
        set_media('IMAGE')                 # 비디오 모드인 채 스틸을 뽑으면 안 된다
        r.filepath = os.path.join(STILLS_DIR, out)
        if samples:
            _try(scene.eevee, "taa_render_samples", int(samples))
        bpy.ops.render.render(write_still=True)
        print("[95_render] still f%d (%s) -> %s"
              % (frame, cam.name if cam else "-", r.filepath))
        return r.filepath
    finally:
        # 복원도 media_type 을 먼저 돌려놔야 file_format 대입이 통과한다
        r.filepath = keep[0]
        if keep[1] is not None:
            _try(r.image_settings, "media_type", keep[1])
        r.image_settings.file_format = keep[2]
        _try(r.image_settings, "color_mode", keep[3])
        _try(scene.eevee, "taa_render_samples", keep[4])


def render_still_all_cams(frame_map=None):
    """4종 카메라 뷰를 각각 스틸로 뽑는다. 카메라 검증용.

    카메라 오브젝트가 존재한다는 사실만으로는 아무것도 보증하지 못한다.
    """
    out = []
    default = {"CAM_Orbital": 40, "CAM_Slowmo": 100, "CAM_Chase": 170,
               "CAM_FPV": 250}
    fm = frame_map or default
    keep_cam = scene.camera
    try:
        for nm, f in fm.items():
            c = bpy.data.objects.get(nm)
            if c is None:
                print("  [경고] %s 없음 — 90_camera.py 를 먼저 실행하라" % nm)
                continue
            scene.camera = c                      # 마커 바인딩을 일시적으로 무시
            out.append(render_still(f, name="cam_%s.png" % nm.replace("CAM_", "")))
    finally:
        scene.camera = keep_cam
    return out


def render_animation():
    """전체 애니메이션 렌더. **사용자 승인 후에만 호출한다.**

    수 분~수십 분 Blender 를 블로킹하며 그동안 MCP 가 응답하지 않는다.
    """
    print("[95_render] 전체 렌더 시작: %d프레임 @%dfps -> %s"
          % (TOTAL, FPS, scene.render.filepath))
    bpy.ops.render.render(animation=True)
    print("[95_render] 렌더 완료 -> %s" % scene.render.filepath)
    return scene.render.filepath


def configure_slowmo_pass(f0, f1, factor=3, path=None):
    """구간 슬로모용 **별도 패스** 설정. 본편과 합치는 것은 ffmpeg 이 한다.

    씬 전역 fps 를 바꾸면 다른 샷의 타이밍이 전부 깨지므로 절대 건드리지 않는다.
    대신 frame_map(출력 프레임 매핑)으로 시간을 늘려 별도 파일로 뽑는다.

        configure_slowmo_pass(364, 424, 3)   # BRAVO 헤어핀 3배 느리게
        render_animation()
        # 이후 원상복구:  apply_final()

    BRAVO_HAIRPIN 이 최저속(0.32 m/s) 구간이라 슬로모 최적 후보다.
    """
    r = scene.render
    r.frame_map_old = 100
    r.frame_map_new = int(100 * factor)
    scene.frame_start, scene.frame_end = int(f0), int(f1 * factor)
    apply_output(path or os.path.join(OUTPUT_DIR,
                                      "slowmo_%d_%d_x%d.mp4" % (f0, f1, factor)))
    print("[95_render] 슬로모 패스: f%d-%d x%d -> %s (끝나면 apply_final() 로 복구)"
          % (f0, f1, factor, r.filepath))


# ==========================================================================
# 6. 적용 + 리포트
# ==========================================================================
apply_final()

_cams = [n for n in ("CAM_Orbital", "CAM_Chase", "CAM_Slowmo", "CAM_FPV")
         if n in bpy.data.objects]
_mk = len(scene.timeline_markers)
_bad_clip = [o.name for o in bpy.data.objects
             if o.type == 'CAMERA' and o.data.clip_start > 0.01]
_est_lo, _est_hi = TOTAL * 0.5 / 60.0, TOTAL * 2.0 / 60.0

print("[95_render] --- 엔진 ---")
print("  %s (%s 세대) | %dx%d @%d%% | %d fps | frames 1-%d (%.1f s) | timeline: %s"
      % (ENGINE, EEVEE_GEN, RES_X, RES_Y, scene.render.resolution_percentage,
         FPS, TOTAL, TOTAL / float(FPS), TIMELINE_SOURCE))
print("  AO/반사=%s | media_type=%s"
      % ("raytracing(Next)" if EEVEE_NEXT else
         ("gtao+ssr(Legacy)" if EEVEE_LEGACY else "★없음★"),
         getattr(scene.render.image_settings, "media_type", "n/a (5.x 이전)")))
print("  taa_render_samples=%s / shadows=%s / motion blur shutter=%.2f steps=%d"
      % (getattr(scene.eevee, "taa_render_samples", "?"),
         getattr(scene.eevee, "use_shadows",
                 getattr(scene.eevee, "use_soft_shadows", "?")),
         MB_SHUTTER, MB_STEPS))
print("  view_transform=%s / look=%s / exposure=%.2f"
      % (scene.view_settings.view_transform, scene.view_settings.look,
         scene.view_settings.exposure))
print("[95_render] --- 출력 ---")
print("  %s (%s/%s, CRF=%s)"
      % (scene.render.filepath, scene.render.ffmpeg.format,
         scene.render.ffmpeg.codec, scene.render.ffmpeg.constant_rate_factor))
print("  카메라 %d/4 %s | 마커 컷 %d개 | 활성 %s"
      % (len(_cams), _cams, _mk, scene.camera.name if scene.camera else "없음"))
if len(_cams) < 4 or _mk == 0:
    print("  [경고] 카메라/마커가 부족하다 — 90_camera.py 를 먼저 실행하라")
if _bad_clip:
    print("  [경고] clip_start > 0.01 인 카메라: %s (근접 샷에서 잘린다)" % _bad_clip)
if TL is None:
    print("  [경고] timeline.json 이 없어 프레임 범위가 추정값이다. **타이밍 미확정**")

print("[95_render] --- 실행 순서 (이 스크립트는 렌더를 시작하지 않는다) ---")
print("  1) render_still(150)            단일 프레임으로 룩 확인")
print("  2) render_still_all_cams()      4종 카메라 뷰 검증")
print("  3) 사용자 승인                   예상 소요 %.0f~%.0f분" % (_est_lo, _est_hi))
print("  4) render_animation()           전체 %d프레임 렌더" % TOTAL)
print("  느리면: apply_preview(50, 8) -> render_animation() 으로 저품질 먼저")

print("[95_render] configured only (no render started) | %s %dx%d %dfps %d frames -> %s"
      % (ENGINE, RES_X, RES_Y, FPS, TOTAL, scene.render.filepath))