---
name: cinematic-render
description: "MAICON 데모 영상의 카메라 리그·라이팅·렌더 설정과 mp4 출력 절차. 오비탈 조감 샷, 차량 추적 체이스 캠, 체크포인트 통과 슬로모, UGV 1인칭 샷의 4종 샷 구성과 컷 편집, EEVEE 렌더 설정, 1080p 30fps 인코딩을 다룬다. 카메라를 배치하거나, 샷을 설계·수정하거나, 라이팅이 어둡다·밋밋하다는 피드백을 반영하거나, 영상을 렌더링·출력하거나, 렌더가 느리다·깨진다는 문제를 해결할 때 반드시 이 스킬을 사용할 것. 차량 자체의 움직임은 ugv-motion 스킬이 담당한다."
---

# 시네마틱 — 카메라 · 라이팅 · 렌더

산출물은 **1080p / 30fps / mp4 데모 영상**이다. 이 스킬의 목표는 기술 시연이 아니라 **경기장이 인상적으로 보이는 것**이다. 축소 모형을 실제 규모처럼 보이게 하는 것이 촬영의 핵심 과제다.

## 1. 축소 모형을 크게 보이게 하는 법

5 m × 3.5 m 디오라마를 그대로 찍으면 장난감처럼 보인다. 원인은 두 가지이고, 둘 다 카메라로 해결한다.

**피사계 심도가 얕으면 모형으로 보인다.** 접사에서 배경이 흐려지는 것은 작은 물체의 특징이다. 조리개를 조여(`aperture_fstop` 4.0 이상) 심도를 깊게 하거나, DOF를 아예 끈다. 예외는 1인칭 샷 — 여기서는 얕은 심도가 오히려 리얼하다.

**시점이 높으면 모형으로 보인다.** 사람이 테이블을 내려다보는 각도가 곧 "모형을 보는 각도"다. 카메라를 **노면 가까이(0.05~0.3 m)** 내리고 초점거리를 길게(35~85 mm) 쓰면 실제 도시를 촬영한 것처럼 보인다. 오비탈 샷조차 가능한 한 낮게 돈다.

```python
cam.data.lens = 50.0            # 표준~망원. 광각(<24mm)은 모형 느낌을 강화한다
cam.data.clip_start = 0.005     # 실측 스케일에서 필수 (기본 0.1m면 근접 샷이 잘린다)
cam.data.clip_end = 50.0
cam.data.dof.use_dof = False    # 기본 끔. 1인칭 샷에서만 켠다
```

## 2. 샷 구성 (`90_camera.py`)

4종 카메라를 만들고 `07_Cameras` 컬렉션에 넣는다. 각 카메라는 독립적으로 애니메이션되며, 컷 편집은 3절의 마커 방식으로 한다.

| 카메라 | 역할 | 구성 |
|--------|------|------|
| `CAM_Orbital` | 트랙 전경 소개 | 경기장 중심을 바라보며 천천히 공전. 높이 1.2 → 0.6 m로 하강 |
| `CAM_Chase` | 차량 추적 | UGV 후방 0.35 m, 높이 0.12 m. 지연 추적으로 부드럽게 |
| `CAM_Slowmo` | 체크포인트 통과 | 체크포인트 옆 고정. 낮은 각도, 통과 순간 슬로모 |
| `CAM_FPV` | UGV 1인칭 | `UGV_Cam`에 부모 고정. 참조 사진의 시점 재현 |

### 오비탈

`Track To` 컨스트레인트로 경기장 중심을 계속 바라보게 한다. 빈 오브젝트를 회전시키고 카메라를 자식으로 두면 궤도가 자동으로 나온다 — 카메라 위치에 직접 키를 찍는 것보다 수정이 쉽다.

```python
pivot = bpy.data.objects.new("CAM_Orbital_pivot", None)
cam.parent = pivot
cam.location = (2.6, 0.0, 1.2)          # 피벗 기준 오프셋
con = cam.constraints.new('TRACK_TO')
con.target = center_empty
con.track_axis, con.up_axis = 'TRACK_NEGATIVE_Z', 'UP_Y'
# 피벗 Z 회전에 키프레임 → 공전
```

### 체이스 캠 — 지연 추적이 핵심

카메라를 차량에 그대로 부모 고정하면 코너에서 화면이 급격히 돌아 어지럽다. **Copy Location 컨스트레인트에 `influence`를 낮추거나**, 차량 뒤를 따라가는 빈 오브젝트를 Follow Path로 별도 주행시키되 **차량보다 약간 느린 진행도**를 주는 방식이 부드럽다. 후자가 관리하기 쉽다:

```python
chase_empty  # UGV와 같은 PATH_Main을 따르되 eval_time을 8프레임만큼 지연
```

차량을 바라보는 것은 `Track To`로 처리한다. 코너에서 카메라가 차량을 놓치지 않으면서도 방향 전환이 부드러워진다.

### 슬로모

체크포인트 통과 구간에서만 시간을 늦춘다. 씬 전체 fps를 바꾸지 말고 **출력 프레임 매핑**을 쓴다. 전역 fps를 건드리면 다른 샷의 타이밍이 전부 깨진다.

통과 프레임은 `_workspace/spec/timeline.json`에서 읽는다. 추정하지 않는다 — 카메라가 통과 순간을 놓치는 원인이 대부분 이 추정이다.

### 1인칭

`UGV_Cam` 빈 오브젝트에 부모 고정하고 로컬 변환은 0으로 둔다. 위치·각도 조정이 필요하면 카메라가 아니라 `UGV_Cam`을 옮긴다 — 모델과 촬영의 책임 분리가 유지된다.

1인칭에서는 DOF를 켜고(`fstop 2.8`) 미세한 손떨림 노이즈를 준다. 실제 주행 영상처럼 보인다.

## 3. 컷 편집 — 마커 바인딩

Blender는 타임라인 마커에 카메라를 바인딩해 자동 전환할 수 있다. VSE 편집보다 간단하고, 렌더 한 번으로 완성 영상이 나온다.

```python
def bind(frame, cam):
    m = scene.timeline_markers.new(f"cut_{frame}", frame=frame)
    m.camera = cam

bind(1,   cams["CAM_Orbital"])   # 트랙 소개
bind(120, cams["CAM_Chase"])     # 주행 시작
bind(140, cams["CAM_Slowmo"])    # ALPHA 통과 (timeline.json 기준)
bind(170, cams["CAM_FPV"])       # 1인칭 주행
bind(330, cams["CAM_Slowmo"])    # BRAVO 통과
bind(360, cams["CAM_Chase"])
bind(458, cams["CAM_Slowmo"])    # CHARLIE 통과
bind(490, cams["CAM_Orbital"])   # 피니시 조감
```

**컷 길이는 최소 40프레임(1.3초) 이상**으로 한다. 그보다 짧으면 시청자가 무엇을 보는지 인식하기 전에 넘어간다. 체크포인트 통과 컷은 통과 프레임의 **8프레임 전**에 시작해야 통과 순간이 컷 안에 들어온다.

## 4. 라이팅

실내 경기장(참조 사진)의 느낌을 기본으로 하되, 데모 영상용으로 대비를 높인다. 균일한 조명은 형태를 납작하게 만든다.

| 조명 | 유형 | 설정 |
|------|------|------|
| `LGT_Key` | Area | 위쪽 45°, 크기 3 m, 강도 200 W, 약간 차가운 백색 |
| `LGT_Fill` | Area | 반대편, 크기 4 m, 강도 60 W, 그림자 완화 |
| `LGT_Rim` | Sun | 낮은 각도, 강도 1.5, 건물 윤곽 강조 |
| 월드 | — | 환경광 0.05, 아주 어두운 회청색 |

**림 라이트가 스카이라인을 만든다.** 건물 윤곽에 밝은 테두리가 생기면 오비탈 샷의 인상이 크게 달라진다. 이것 하나가 라이팅 작업의 절반이다.

그림자는 반드시 켠다. 그림자가 없으면 객체가 공중에 뜬 것처럼 보이고, 축소 모형에서는 이 효과가 특히 크다.

## 5. 렌더 설정 (`95_render.py`)

**EEVEE를 쓴다.** Cycles는 이 씬에서 프레임당 수십 초가 걸려 600프레임 렌더가 몇 시간이 된다. 데모 영상의 룩은 EEVEE로 충분하다.

```python
scene.render.engine = 'BLENDER_EEVEE_NEXT'   # 4.2+ / 구버전은 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
scene.render.resolution_percentage = 100
scene.render.fps = 30
scene.frame_start, scene.frame_end = 1, 600

scene.eevee.taa_render_samples = 32          # 소형 디테일(차선 15mm) 앨리어싱 방지
scene.eevee.use_shadows = True

scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.ffmpeg.constant_rate_factor = 'HIGH'
scene.render.ffmpeg.ffmpeg_preset = 'GOOD'
scene.render.filepath = "/Users/robin/Downloads/maicon-sim/output/maicon_demo.mp4"
```

`taa_render_samples`를 32 이상으로 두는 이유는 차선 폭이 15 mm에 불과해 낮은 샘플에서 계단 현상이 심하게 보이기 때문이다.

### 렌더 실행 — 반드시 확인 후에

`bpy.ops.render.render(animation=True)`는 **수 분에서 수십 분간 Blender를 블로킹**한다. MCP 연결이 그동안 응답하지 않으므로, 실행 전에 다음을 지킨다:

1. 먼저 **단일 프레임 테스트 렌더**로 룩을 확인한다 (`scene.frame_set(150)` 후 스틸 렌더)
2. 스틸이 만족스러울 때만 전체 애니메이션 렌더로 넘어간다
3. 전체 렌더는 **사용자에게 예상 소요를 알리고 확인을 받은 뒤** 실행한다

이 순서를 지키지 않으면 잘못된 룩으로 30분을 태우고 처음부터 다시 하게 된다.

프리뷰가 필요하면 `resolution_percentage = 50`과 `taa_render_samples = 8`로 저품질 빠른 렌더를 먼저 뽑는다.

## 6. 검증 기준

- [ ] 4종 카메라가 모두 존재하고 각각의 뷰에서 트랙이 프레임 안에 들어온다
- [ ] `clip_start`가 0.01 이하 (근접 샷 잘림 방지)
- [ ] 컷 전환이 체크포인트 통과 프레임과 어긋나지 않는다 (`timeline.json` 대조)
- [ ] 모든 컷이 40프레임 이상이다
- [ ] 카메라가 건물이나 노면을 관통하는 구간이 없다
- [ ] 테스트 스틸에서 그림자·림 라이트가 보인다
- [ ] 출력 파일이 실제로 생성되고 재생 가능하다

카메라 검증은 각 카메라 뷰로 전환해 스크린샷을 찍어 확인한다. 카메라 오브젝트가 존재한다는 사실만으로는 아무것도 보증하지 못한다.

## 7. 재작업 지침

- "어둡다" → `LGT_Key` 강도와 월드 환경광을 먼저 조정. 노출(`view_settings.exposure`)은 마지막 수단
- "밋밋하다" → 림 라이트 강화, 카메라 높이 하강, 초점거리 증가 순으로 시도
- "장난감처럼 보인다" → 1절의 두 원인(얕은 심도, 높은 시점)을 점검
- "렌더가 너무 느리다" → Cycles를 쓰고 있는지 먼저 확인. EEVEE에서 느리면 샘플 수와 해상도 배율을 낮춰 프리뷰
- 컷 타이밍 수정은 3절의 `bind` 목록만 고치면 된다. 카메라 애니메이션은 건드리지 않는다
