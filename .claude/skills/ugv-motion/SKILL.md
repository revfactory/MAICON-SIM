---
name: ugv-motion
description: "UGV 차량이 트랙을 주행하는 애니메이션 제작 절차. 베지어 주행 경로 생성, Follow Path 컨스트레인트, 속도 곡선과 코너 감속, 바퀴 회전 동기화, 차체 롤·피치, 체크포인트 통과 타이밍, 포트홀 회피를 다룬다. 주행 애니메이션을 만들거나, 경로를 수정하거나, 차량이 미끄러진다·바퀴가 안 돈다·너무 빠르다·코너를 이상하게 돈다는 피드백을 반영하거나, 랩타임·통과 시점을 조정할 때 반드시 이 스킬을 사용할 것. 카메라 움직임은 cinematic-render 스킬이 담당한다."
---

# UGV 모션 — 주행 경로와 애니메이션

데모 영상의 설득력은 차량이 **물리적으로 그럴듯하게 움직이는가**에 달려 있다. 등속으로 미끄러지듯 도는 차량은 즉시 가짜로 보인다. 이 스킬은 그 문제를 세 가지로 나눠 해결한다: 경로, 속도, 부수 운동(바퀴·차체).

## 1. 주행 경로 (`80_motion.py`)

경로는 베지어 커브 `PATH_Main`으로 만든다. 제어점은 `track-geometry` 스킬의 `references/track-coordinates.md` 5절 "주행 경로 구조"에서 가져온다.

```python
curve = bpy.data.curves.new("PATH_Main_crv", 'CURVE')
curve.dimensions = '3D'
spline = curve.splines.new('BEZIER')
spline.bezier_points.add(len(PTS) - 1)
for bp, (x, y) in zip(spline.bezier_points, PTS):
    bp.co = (x, y, 0.0)
    bp.handle_left_type = bp.handle_right_type = 'AUTO'
spline.use_cyclic_u = False          # START→FINISH는 열린 경로
path = bpy.data.objects.new("PATH_Main", curve)
```

**경로가 만족해야 하는 조건:**
- START에서 시작해 FINISH에서 끝난다 (닫힌 루프가 아니다)
- ALPHA · BRAVO · CHARLIE 체크포인트를 0.05 m 이내로 통과한다
- 포트홀 2곳에서 `포트홀 반경 + 차폭 절반(0.065) + 여유 0.02` 이상 떨어진다
- 곡률 반경이 최소 0.25 m 이상이다 — 그보다 급하면 차량이 제자리 회전하는 것처럼 보인다

포트홀 회피는 경로를 통째로 다시 그리지 말고 **해당 구간에 우회 제어점 2개를 삽입**한다. 전체를 다시 그리면 체크포인트 통과가 깨진다.

```python
def clearance_ok(pt, potholes, margin=0.085):
    return all((pt[0]-p["pos"][0])**2 + (pt[1]-p["pos"][1])**2 > (p["r"]+margin)**2
               for p in potholes)
```

## 2. Follow Path 컨스트레인트

`UGV_Root`에만 컨스트레인트를 건다. 부품은 루트의 자식이므로 따라온다.

```python
con = root.constraints.new('FOLLOW_PATH')
con.target = path
con.use_curve_follow = True      # 진행 방향으로 자동 회전 — 이게 꺼져 있으면 차가 옆으로 간다
con.up_axis = 'UP_Z'

# 전방 축은 추측하지 말고 차량이 선언한 값을 읽는다.
# 모델의 전방과 어긋나면 차가 옆으로 또는 뒤로 간다.
axis = root.get("forward_axis", "+X")            # 70_vehicle.py가 심어 둔 커스텀 프로퍼티
con.forward_axis = {"+X": 'FORWARD_X', "+Y": 'FORWARD_Y',
                    "-X": 'TRACK_NEGATIVE_X', "-Y": 'TRACK_NEGATIVE_Y'}[axis]
```

**전방 축을 하드코딩하지 않는 것이 중요하다.** 모델러가 차량 전방을 어느 축으로 잡았는지는 모델링 단계의 결정이고, 애니메이션이 그것을 추측하면 조용히 어긋난다. 증상(차가 옆으로 감)과 원인(축 불일치)의 거리가 멀어 디버깅이 오래 걸린다.

`use_curve_follow`를 켜면 커브의 **틸트**가 차량 자세에 반영된다. 커브 제어점의 tilt를 0으로 유지해야 차가 기울지 않는다. 코너 뱅킹을 주고 싶다면 tilt를 쓰지 말고 3절의 롤 방식을 쓴다 — tilt는 경로 수정 때마다 다시 잡아야 해서 관리 비용이 크다.

## 3. 속도 곡선 — 등속을 피한다

`eval_time`(경로 진행도)에 키프레임을 찍어 속도를 만든다. 선형 보간이면 등속이 되어 부자연스럽다.

**속도 설계 원칙:** 직선에서 가속, 코너 진입 전 감속, 코너 탈출 시 재가속. 체크포인트 근처에서는 살짝 느리게 — 데모 영상에서 통과 순간이 보여야 하기 때문이다.

```python
path.data.use_path = True
path.data.path_duration = TOTAL_FRAMES

# 구간별 진행도 키: (frame, eval_time_0~1)
KEYS = [(1, 0.00), (60, 0.09), (110, 0.22), (150, 0.28),   # ALPHA 근처 감속
        (240, 0.46), (300, 0.55), (340, 0.61),              # BRAVO
        (430, 0.78), (470, 0.84),                           # CHARLIE
        (560, 0.97), (600, 1.00)]
for f, t in KEYS:
    path.data.eval_time = t * TOTAL_FRAMES
    path.data.keyframe_insert("eval_time", frame=f)

for fc in path.data.animation_data.action.fcurves:
    for kp in fc.keyframe_points:
        kp.interpolation = 'BEZIER'
        kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
```

`AUTO_CLAMPED`가 중요하다. 기본 `AUTO` 핸들은 키 사이에서 오버슈트를 만들어 **차량이 잠깐 뒤로 갔다가 다시 가는** 현상을 일으킨다.

**단조 증가 검증:** 키프레임의 `eval_time`이 프레임 순서대로 반드시 증가해야 한다. 하나라도 역전되면 차가 후진한다. 스크립트 끝에서 검산한다:

```python
assert all(KEYS[i][1] < KEYS[i+1][1] for i in range(len(KEYS)-1)), "eval_time 역전"
```

## 4. 바퀴 회전 — 속도와 동기화

바퀴가 안 도는 차량은 데모에서 가장 먼저 눈에 띄는 결함이다. 반대로 **속도와 무관하게 도는 바퀴**(등속 회전)도 미끄러져 보인다. 실제 이동 거리에서 회전각을 계산한다.

```python
WHEEL_R = 0.022                       # 바퀴 반경 22 mm
# 프레임별로 루트의 실제 이동 거리를 누적해 회전각 산출
angle = 0.0
prev = None
for f in range(1, TOTAL_FRAMES + 1):
    scene.frame_set(f)
    p = root.matrix_world.translation.copy()
    if prev is not None:
        angle += (p - prev).length / WHEEL_R      # rad = 거리 / 반경
    prev = p
    for w in wheels:
        w.rotation_euler.x = angle
        w.keyframe_insert("rotation_euler", index=0, frame=f)
```

`scene.frame_set(f)`로 컨스트레인트가 평가된 **실제 월드 위치**를 읽는 것이 핵심이다. 컨스트레인트는 의존성 그래프가 평가되어야 위치에 반영되므로, 프레임을 설정하지 않고 `matrix_world`를 읽으면 전부 같은 값이 나온다.

이 루프는 프레임 수만큼 의존성 그래프를 평가하므로 600 프레임 기준 수 초가 걸린다. 정상이다.

## 5. 차체 부수 운동

미세한 움직임이 "살아있는 느낌"을 만든다. 과하면 장난감처럼 보이므로 진폭을 작게 유지한다.

| 운동 | 구현 | 진폭 |
|------|------|------|
| 코너 롤 | 경로 곡률에 비례해 `UGV_Body`의 로컬 Y 회전 | 최대 3° |
| 가감속 피치 | 속도 변화율에 비례해 로컬 X 회전 | 최대 2° |
| 노면 진동 | 노이즈 모디파이어를 Z 위치 F커브에 추가 | 0.5 mm |

노면 진동은 F커브 모디파이어로 준다. 키프레임을 수백 개 찍는 것보다 가볍고 수정이 쉽다:

```python
fc = body.animation_data.action.fcurves.find("location", index=2)
nm = fc.modifiers.new('NOISE')
nm.strength = 0.0005
nm.scale = 3.0
```

**포트홀 통과 시**에는 진폭을 키운다. 회피하는 것이 원칙이지만, 데모에서 한 번쯤 근접 통과하며 차체가 흔들리면 위험 요소의 존재가 전달된다.

## 6. 체크포인트 통과 이벤트

각 체크포인트를 통과하는 프레임을 계산해 `_workspace/spec/timeline.json`에 기록한다. 카메라 컷과 자막 타이밍이 이 값을 참조하므로, 애니메이션이 바뀌면 이 파일도 갱신해야 한다.

```json
{
  "total_frames": 600, "fps": 30,
  "events": [
    {"name": "START",   "frame": 1},
    {"name": "ALPHA",   "frame": 148},
    {"name": "BRAVO",   "frame": 337},
    {"name": "CHARLIE", "frame": 466},
    {"name": "FINISH",  "frame": 600}
  ]
}
```

통과 프레임은 추정하지 말고 **실제 궤적에서 측정**한다. 각 프레임의 루트 위치와 체크포인트 좌표의 거리를 계산해 최소가 되는 프레임을 찾는다. 추정값을 쓰면 카메라가 통과 순간을 놓친다.

## 7. 검증 기준

- [ ] 차량이 경로를 따라 START → FINISH로 **단조 진행**한다 (후진·정지 구간 없음)
- [ ] 체크포인트 3곳을 모두 0.05 m 이내로 통과한다
- [ ] 포트홀과 최소 거리가 0.085 m 이상이다
- [ ] 바퀴 회전이 이동 거리와 일치한다 (미끄러짐 없음). 정지 시 바퀴도 정지
- [ ] 차량이 노면을 뚫거나 공중에 뜨지 않는다 (Z ≈ 바퀴 반경)
- [ ] 차량 진행 방향이 전방을 향한다 (옆으로/뒤로 가지 않음)
- [ ] `timeline.json`의 이벤트 프레임이 실측값이다

검증은 프레임 몇 개를 골라 스크린샷으로 확인한다. 특히 **코너 구간과 체크포인트 통과 프레임**을 본다. 직선 구간만 보면 방향 오류를 놓친다.

## 8. 재작업 지침

- "너무 빨라/느려" → `TOTAL_FRAMES`와 `KEYS`의 진행도만 조정. 경로는 건드리지 않는다
- "코너에서 이상해" → 해당 구간의 제어점 핸들을 `AUTO`에서 조정하거나 제어점을 1개 추가
- "바퀴가 미끄러져" → `WHEEL_R`이 실제 바퀴 지오메트리와 맞는지 확인
- 경로를 수정하면 **4·6절을 반드시 재실행**한다. 바퀴 회전과 이벤트 프레임이 경로에 의존하기 때문이다. 이 재실행을 빠뜨리면 바퀴가 옛 경로 기준으로 돌아 미끄러진다
