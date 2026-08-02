---
name: track-geometry
description: "MAICON 본선 경기장(5m×3.5m) 트랙의 좌표 스펙 확정과 노면 지오메트리 제작 절차. 도면 판독→월드 좌표 변환, 도로 중심선·노란/흰 차선·START/FINISH·헬리패드·포트홀·배리어 제작, 아스팔트 머티리얼 구성을 다룬다. 트랙 좌표를 정하거나, 노면·차선·도로 마킹·포트홀·배리어를 만들거나, 경기장 치수를 검증하거나, 좌표가 틀렸다는 지적을 받아 수정할 때 반드시 이 스킬을 사용할 것. 건물·객체·차량 모델링은 procedural-assets 스킬이 담당한다."
---

# 트랙 지오메트리 — 좌표 스펙과 노면 제작

경기장은 **가로 5 m × 세로 3.5 m**다. Blender 1 unit = 1 m 실측 스케일을 그대로 쓴다 (`blender-mcp-protocol` 8항).

좌표 원본은 `references/track-coordinates.md`에 있다. **좌표를 새로 눈대중하지 말고 그 표를 단일 출처로 삼는다.** 표가 틀렸다고 판단되면 표를 고치고, 고친 사실을 기록한다. 좌표가 여러 곳에 흩어지면 이후 배치·애니메이션이 전부 어긋난다.

## 1. 좌표 스펙 산출 (track-surveyor)

`00_common.py`에 `SPEC` 딕셔너리를 생성한다. 이것이 이후 모든 스크립트가 참조하는 **단일 진실 공급원**이다.

```python
SPEC = {
    "arena": {"w": 5.0, "h": 3.5, "border": 0.06},
    "road":  {"lane_w": 0.30, "line_w": 0.015, "line_z": 0.0005},
    "checkpoints": {
        "ALPHA":   {"pos": (-1.15,  1.63), "color": (0.9, 0.1, 0.1)},
        "BRAVO":   {"pos": (-0.39, -0.13), "color": (0.1, 0.8, 0.2)},
        "CHARLIE": {"pos": (-1.55, -1.64), "color": (0.15, 0.35, 0.95)},
    },
    "sectors": { "1": {"pos": (-0.45, 1.09), ...}, ... },
    "objects": [ {"id": 1, "pos": (x, y), "yaw": 0.0}, ... ],   # 23개
    "potholes": [ {"pos": (-1.03, 0.15), "r": 0.11}, ... ],     # 2개
    "barriers": [ {"pos": (-1.03, 0.59), "yaw": 0.0}, ... ],    # 2개
    "helipad": {"pos": (-1.95, 0.80), "size": (0.50, 0.44)},
    "start":   {"pos": (-2.35, 1.33), "yaw": 0.0},
    "finish":  {"pos": ( 2.23, -1.68), "yaw": 0.0},
}
```

`SPEC`은 파이썬 리터럴로 스크립트에 직접 쓰고, 동시에 `_workspace/spec/track_spec.json`으로도 저장한다. JSON 사본이 있어야 다른 에이전트가 Blender 없이 좌표를 읽을 수 있다. **두 사본이 어긋나면 모든 검증이 무의미해지므로, JSON을 먼저 쓰고 스크립트가 그것을 읽어 들이는 방식을 택한다:**

```python
import json, os
SPEC = json.load(open(os.path.join(WORKSPACE, "spec", "track_spec.json")))
```

### 도면 판독 절차

도면 이미지는 5:3.5 = 1.4286 비율이고, 참조 이미지 해상도는 2000×1400 px로 같은 비율이다. 따라서 픽셀↔미터 변환이 선형이다:

```
x_m = (px / 2000) * 5.0 - 2.5
y_m = 1.75 - (py / 1400) * 3.5
```

판독한 좌표는 **반드시 검산한다**. 검산 없이 확정하면 좌우 반전이나 Y축 부호 오류가 끝까지 살아남는다:
- START는 좌측 상단(x<0, y>0), FINISH는 우측 하단(x>0, y<0)이어야 한다
- ALPHA는 상단 중앙부, CHARLIE는 하단 좌측, BRAVO는 중앙부에 온다
- Sector 1·2는 상단 좌중앙, Sector 3·4는 상단 우측, Sector 7은 좌하단
- 모든 좌표가 `|x| ≤ 2.5`, `|y| ≤ 1.75` 안에 들어온다

## 2. 노면 제작 (track-builder)

### 2-1. 베이스 (`10_ground.py`)

경기장 바닥은 단순 평면이 아니라 **얕은 트레이 형태**다 (참조 사진의 테이블 레이아웃). 바닥 평면 + 테두리 프레임으로 만든다.

- `GND_Base`: 5.0 × 3.5 평면, Z=0
- `GND_Frame`: 테두리 프레임, 폭 60 mm, 높이 40 mm, 짙은 회색

아스팔트 머티리얼(`MAT_Asphalt`)은 균일한 회색이면 가짜처럼 보인다. 노이즈 텍스처로 미세한 명암 편차와 러프니스 변화를 준다:

```python
mat = get_or_create_material("MAT_Asphalt")
nt = mat.node_tree
bsdf = nt.nodes["Principled BSDF"]
noise = nt.nodes.new("ShaderNodeTexNoise")
noise.inputs["Scale"].default_value = 220.0
noise.inputs["Detail"].default_value = 6.0
ramp = nt.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].color = (0.045, 0.045, 0.048, 1)   # 어두운 아스팔트
ramp.color_ramp.elements[1].color = (0.085, 0.085, 0.090, 1)
nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
bsdf.inputs["Roughness"].default_value = 0.82
```

### 2-2. 도로 마킹 (`20_markings.py`)

마킹은 노면에서 **0.5 mm 띄운 평면**으로 만든다. 같은 높이면 Z-파이팅이 난다.

| 요소 | 색 | 폭 | 비고 |
|------|-----|-----|------|
| 주행 차선 (노랑) | `(0.95, 0.78, 0.05)` | 15 mm | 트랙 주 경로. 곡선 구간은 베지어 |
| 차로 구분선 (흰색) | `(0.92, 0.92, 0.92)` | 12 mm | 도로 중앙/교차로 |
| START 라인 | 흰색 | 20 mm | 좌상단, 사각 브래킷 표식 동반 |
| FINISH | 노랑/검정 사선 | — | 우하단, 배리어와 인접 |
| 헬리패드 | 검정 판 + 주황 링 + 흰 H | 500×440 mm | 좌상단 |

곡선 차선은 베지어 커브에 **bevel object(사각 단면)를 적용**해 만든다. 폴리곤을 손으로 배치하는 것보다 정확하고 수정이 쉽다:

```python
curve = bpy.data.curves.new("MRK_Lane_Outer_crv", 'CURVE')
curve.dimensions = '3D'
curve.bevel_depth = 0.0075          # 폭 15 mm의 절반
curve.bevel_resolution = 2
spline = curve.splines.new('BEZIER')
spline.bezier_points.add(len(points) - 1)
for bp, (x, y) in zip(spline.bezier_points, points):
    bp.co = (x, y, SPEC["road"]["line_z"])
    bp.handle_left_type = bp.handle_right_type = 'AUTO'
```

`AUTO` 핸들은 부드러운 곡선을 자동으로 만들어 준다. 직선 구간이 필요하면 해당 점만 `'VECTOR'`로 바꾼다.

**트랙 경로 구조:** 노란 선은 외곽 순환로 1개 + 각 섹터 블록을 감싸는 서브 루프 4개로 구성된다. 중앙 십자 교차로(세로선 x≈0.56, 가로선 y≈0.18)가 구역을 나눈다. 각 루프의 제어점 목록은 `references/track-coordinates.md`의 "경로 폴리라인" 절에 있다.

### 2-3. 위험 요소 (`30_hazards.py`)

**포트홀 2곳** — 단순 검은 원판이 아니라 실제로 파인 형태로 만들어야 조명에서 그럴듯하다. 원판을 아래로 눌러 오목하게 만들고, 가장자리에 불규칙한 균열을 붙인다:

```python
# 오목한 포트홀: 중심 정점을 아래로
verts, faces = disc_verts(radius=r, segments=24, center_z=-0.008)
```

**배리어 2곳** — 노랑/검정 사선 줄무늬 판. 출발 직후와 FINISH 직전에 놓인다. 폭 약 260 mm, 높이 25 mm의 낮은 턱 형태다.

**노면 균열** — 도면 곳곳의 검은 균열 무늬는 지오메트리가 아니라 **머티리얼 데칼**로 처리한다. 별도 평면에 알파 텍스처를 얹어 노면 위 0.3 mm에 배치한다. 지오메트리로 만들면 폴리곤만 늘고 시각적 이득이 없다.

## 3. 검증 기준

트랙 빌드 후 다음을 확인한다. 개수만으로 통과시키지 않는다 — 좌표 오류는 개수를 바꾸지 않는다.

- [ ] 베이스 치수가 정확히 5.0 × 3.5 m (`obj.dimensions` 출력으로 확인)
- [ ] 모든 마킹의 Z가 0.0005 ± 0.0002 (Z-파이팅 방지)
- [ ] 차선이 경기장 밖으로 나가지 않음 (`|x| ≤ 2.5`, `|y| ≤ 1.75`)
- [ ] 톱 뷰 스크린샷이 원본 도면과 좌우·상하 방향이 일치 (반전 없음)
- [ ] START가 좌상단, FINISH가 우하단
- [ ] 포트홀 2개, 배리어 2개 (명세 고정 수량)
- [ ] 체크포인트 3개가 각각 주행 경로 위에 위치 (경로에서 벗어나면 통과 판정 불가)

## 4. 재작업 지침

좌표 수정 요청을 받으면 **`_workspace/spec/track_spec.json`만 고치고 스크립트를 재실행**한다. 스크립트에 좌표를 하드코딩하지 않은 이유가 이것이다. 수정 후 영향받는 단계(20→30→55→80)를 순서대로 재실행한다 — 객체 배치와 주행 경로가 좌표에 의존하므로 트랙만 고치면 어긋난다.
