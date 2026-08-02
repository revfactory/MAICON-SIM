---
name: blender-mcp-protocol
description: "Blender MCP(execute_blender_code / get_scene_info / get_viewport_screenshot)를 안전하게 쓰기 위한 공유 규약. 씬 충돌 방지, 멱등 스크립트 작성, 컬렉션·명명 규약, bpy.ops 회피, 청크 실행, 연결 복구, 스크린샷 검증 절차를 정의한다. Blender에 파이썬 코드를 실행하거나, 빌드 스크립트를 작성하거나, 씬을 수정·검증하는 모든 작업에서 반드시 먼저 이 스킬을 읽을 것. MAICON 시뮬레이터의 모든 에이전트가 공유하는 기반 규약이다."
---

# Blender MCP 프로토콜 — 공유 규약

MAICON 시뮬레이터의 모든 에이전트가 따르는 Blender 조작 규약이다. 이 규약이 존재하는 이유는 하나다: **Blender MCP는 살아있는 단일 Blender 인스턴스를 조작한다.** 파일 편집과 달리 되돌리기가 어렵고, 두 주체가 동시에 건드리면 결과가 예측 불가능해진다.

## 1. 황금 규칙 — 스크립트를 쓰고, 실행은 오케스트레이터에게 맡긴다

**빌드 에이전트는 `execute_blender_code`를 호출하지 않는다.** 담당 모듈의 Blender Python 스크립트를 `_workspace/scripts/{NN}_{module}.py`에 **파일로 작성**하고 종료한다. 실행은 오케스트레이터가 정해진 번호 순서대로 하나씩 수행한다.

이유:
- 여러 에이전트가 동시에 씬을 수정하면 오브젝트 이름 충돌, 컬렉션 경합, 선택 상태 간섭이 발생한다. 디버깅이 사실상 불가능해진다.
- 스크립트가 파일로 남으면 씬 전체가 **결정적으로 재생성**된다. Blender가 죽거나 씬이 망가져도 처음부터 다시 빌드하면 같은 결과가 나온다. 이 재현성이 3D 작업에서 가장 값비싼 자산이다.
- 부분 수정이 저렴해진다. "건물 높이만 다시"는 `40_sectors.py`만 고쳐 재실행하면 된다.

**예외:** `scene-inspector`는 검증 목적의 **읽기 전용 조회 코드**(좌표·치수 출력, 통계 집계)를 직접 실행할 수 있다. 단, 씬을 수정하는 코드는 실행하지 않고 담당 에이전트에게 수정을 요청한다.

## 2. 스크립트 실행 순서 (고정)

| 순서 | 파일 | 담당 에이전트 | 내용 |
|------|------|-------------|------|
| 00 | `00_common.py` | track-surveyor | 공통 헬퍼 + 좌표 상수. 항상 먼저 실행 |
| 10 | `10_ground.py` | track-builder | 베이스 플레이트, 아스팔트 머티리얼 |
| 20 | `20_markings.py` | track-builder | 노란/흰 차선, START/FINISH, 헬리패드 |
| 30 | `30_hazards.py` | track-builder | 포트홀 2곳, 배리어 2곳, 노면 균열 |
| 40 | `40_sectors.py` | asset-modeler | Sector 1~9 건물 |
| 50 | `50_objects.py` | asset-modeler | 객체 7종 프로토타입 |
| 60 | `60_markers.py` | asset-modeler | ArUco 마커 보드 프로토타입 |
| 55 | `55_placement.py` | scene-dresser | 객체 23곳 배치 + 마커 짝 배치 + 체크포인트 |
| 70 | `70_vehicle.py` | asset-modeler | UGV 차량 |
| 80 | `80_motion.py` | motion-director | 주행 경로 + 애니메이션 |
| 90 | `90_camera.py` | cinematographer | 카메라 리그 + 라이팅 |
| 95 | `95_render.py` | cinematographer | 렌더 설정 + mp4 출력 |

**번호 순서와 실행 순서가 한 곳에서 어긋난다.** `55_placement`는 번호상 60보다 앞이지만 **60 다음에 실행**한다 — 배치가 마커 보드 프로토타입을 필요로 하기 때문이다. 실행 순서는 위 표의 행 순서를 따른다:

```
00 → 10 → 20 → 30 → 40 → 50 → 60 → 55 → 70 → 80 → 90 → 95
```

번호 사이에 여유(01~09, 11~19 …)를 남긴 것은 나중에 모듈을 끼워 넣기 위함이다.

## 3. 멱등성 — 모든 스크립트는 재실행 가능해야 한다

스크립트를 두 번 실행해도 결과가 같아야 한다. 그렇지 않으면 부분 재빌드가 불가능해지고, Blender가 `Cube.001`, `Cube.002` 같은 유령 오브젝트를 쌓는다. **이 접미사 충돌이 이후 모든 이름 참조를 조용히 깨뜨리는 최대 원인이다.**

모든 스크립트는 생성 전에 자기 담당 접두사를 지운다:

```python
def purge(prefix):
    """이 스크립트가 만드는 오브젝트를 먼저 제거해 재실행을 안전하게 만든다."""
    for o in [o for o in bpy.data.objects if o.name.startswith(prefix)]:
        bpy.data.objects.remove(o, do_unlink=True)
    for m in [m for m in bpy.data.meshes if m.users == 0]:
        bpy.data.meshes.remove(m)
```

머티리얼은 이름으로 재사용한다 (지우고 다시 만들면 다른 스크립트의 참조가 끊긴다):

```python
def get_or_create_material(name):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
    return mat
```

## 4. bpy.ops를 피하고 bpy.data를 쓴다

`bpy.ops.*`는 **화면의 컨텍스트**(활성 오브젝트, 마우스가 있는 영역, 현재 모드)에 의존한다. MCP로 실행하면 그 컨텍스트가 없거나 예상과 달라 `RuntimeError: context is incorrect`로 실패하거나, 더 나쁘게는 엉뚱한 오브젝트에 적용된다.

```python
# 취약 — 컨텍스트 의존
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 1))

# 견고 — 데이터 API 직접 조작
mesh = bpy.data.meshes.new("SEC_01_mesh")
mesh.from_pydata(verts, [], faces)
mesh.update()
obj = bpy.data.objects.new("SEC_01_Tower", mesh)
bpy.context.scene.collection.objects.link(obj)
obj.location = (0.0, 0.0, 1.0)
```

**불가피하게 bpy.ops를 써야 할 때**(모디파이어 적용, 부울 연산 일부)는 컨텍스트 오버라이드로 감싼다:

```python
with bpy.context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
    bpy.ops.object.modifier_apply(modifier="Bevel")
```

박스·실린더처럼 반복되는 형상은 `from_pydata` 헬퍼로 만들어 두고 재사용한다. `00_common.py`가 `make_box()`, `make_cylinder()`, `make_plane()`을 제공한다.

## 5. 컬렉션 계층과 명명 규약

씬이 커지면 아웃라이너가 난장판이 되어 검증과 수정이 급격히 느려진다. 모든 오브젝트는 지정된 컬렉션에 들어간다.

```
MAICON
├── 00_Ground      GND_*
├── 01_Markings    MRK_*
├── 02_Hazards     HZD_*
├── 03_Sectors     SEC_*
├── 04_Objects     OBJ_*
├── 05_Markers     ARU_*
├── 06_Vehicle     UGV_*
├── 07_Cameras     CAM_*
└── 08_Lights      LGT_*
```

명명은 `{접두사}_{식별자}_{부품}` 형태로 한다: `SEC_03_TowerB`, `OBJ_11_tank`, `HZD_Pothole_01`, `ARU_07_Board`.

객체 인스턴스는 **포지션 번호를 이름에 박는다** (`OBJ_11_tank` = 11번 포지션의 전차). 나중에 "몇 번 자리에 무엇이 있는가"를 이름만으로 조회할 수 있어 검증이 쉬워진다.

## 6. 스크립트 표준 구조

모든 빌드 스크립트는 이 형태를 따른다. `00_common.py`를 `exec`로 로드하는 이유는, MCP 실행 환경에는 모듈 검색 경로가 잡혀 있지 않아 `import`가 실패하기 때문이다.

```python
import bpy, os

WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
exec(open(os.path.join(WORKSPACE, "scripts", "00_common.py")).read())
# 이후 SPEC(좌표 딕셔너리), purge(), make_box(), link_to() 등을 사용할 수 있다

purge("SEC_")
col = link_collection("03_Sectors")

# ... 생성 코드 ...

print(f"[40_sectors] built {len(col.objects)} objects")
```

마지막 `print`는 반드시 남긴다. MCP는 표준 출력을 돌려주므로, 이 한 줄이 "실행됐는지"와 "몇 개 만들었는지"를 알려주는 유일한 신호다.

## 7. 실행 규약 (오케스트레이터용)

### 청크 분할
`execute_blender_code`에 아주 긴 코드를 한 번에 보내면 전송 실패나 타임아웃이 난다. 스크립트를 파일로 두고 **짧은 로더**만 보낸다:

```python
exec(open("/Users/robin/Downloads/maicon-sim/_workspace/scripts/40_sectors.py").read())
```

이 방식이면 스크립트 길이에 상관없이 안전하고, 스크립트 수정 후 같은 로더를 다시 보내면 재실행된다.

### exec 네임스페이스는 호출 간 유지되지 않는다

`exec()`로 로드한 함수는 **그 호출 안에서만** 존재한다. 다음 `execute_blender_code`에서 부르면 `NameError`가 난다. 스크립트가 정의한 함수(`render_still`, `render_animation` 등)를 쓰려면 **같은 블록에서 스크립트를 다시 로드**한다:

```python
exec(open(".../95_render.py").read())
render_still(150)          # 같은 블록이라야 보인다
```

씬 상태(오브젝트·머티리얼·설정)는 Blender에 남으므로 재로드는 저렴하다. 사라지는 것은 파이썬 이름뿐이다.

### 장시간 렌더는 MCP 타임아웃을 넘긴다

전체 애니메이션 렌더는 수십 분 걸리고 그동안 Blender가 MCP에 응답하지 않는다. 호출은 타임아웃되어 백그라운드로 전환되지만 **Blender 내부에서는 렌더가 계속된다.** 타임아웃을 실패로 오인해 재실행하면 같은 렌더가 두 번 돌아 파일이 깨진다.

완료 판별은 **출력 파일의 존재와 크기**로 한다. 렌더 시작 전에 이전 산출물을 지워 두면 판별이 명확해진다.

### 실행 후 검증 (매 단계 필수)
1. 반환된 `print` 출력에서 생성 개수를 확인한다
2. `get_scene_info`로 오브젝트 총수를 확인한다
3. 시각 변화가 있는 단계는 `get_viewport_screenshot`으로 눈으로 확인한다

**개수만 맞다고 통과시키지 않는다.** 좌표가 100배 틀려도 개수는 맞다. 스크린샷이 유일한 실질 검증 수단이다.

### 연결 실패 대응
`Could not connect to Blender`가 반환되면 애드온이 꺼져 있는 것이다. 코드를 고치지 말고 **사용자에게 Blender 실행과 애드온 활성화를 요청한다** (Blender 실행 → N 패널 → BlenderMCP → Connect). 재시도는 사용자 확인 후 1회.

## 8. 씬 초기 설정

`00_common.py`가 담당한다. 5m × 3.5m 실측 스케일을 그대로 Blender 단위(1 unit = 1 m)로 쓴다. 축소 스케일을 쓰면 이후 모든 좌표 계산에 환산이 끼어들어 실수를 부른다.

```python
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
scene.unit_settings.length_unit = 'METERS'
```

이 실측 스케일에서 주의할 점:
- 카메라 `clip_start`를 **0.01 이하**로 낮춘다. 기본값 0.1m면 근접 샷에서 지오메트리가 잘린다.
- 차선 폭(약 15mm), 마커 보드(약 40mm) 같은 소형 디테일은 뷰포트 기본 클리핑에서도 보이지만, 렌더 시 안티에일리어싱 샘플을 충분히 줘야 깨지지 않는다.
- 노면 마킹은 별도 지오메트리 대신 **Z를 0.5mm 띄운 평면**으로 만든다. 같은 높이면 Z-파이팅으로 렌더가 지저분해진다.

## 9. 좌표계 규약

- 원점: 트랙 정중앙 (도면의 정중앙)
- X: 도면 가로, 오른쪽이 +. 범위 `-2.5 ~ +2.5` (5 m)
- Y: 도면 세로, 위쪽(북)이 +. 범위 `-1.75 ~ +1.75` (3.5 m)
- Z: 높이, 노면이 0

도면 픽셀에서 월드 좌표로의 변환은 `track-geometry` 스킬의 `references/track-coordinates.md`에 정의되어 있다. 좌표를 새로 추정하지 말고 그 표를 단일 출처로 삼는다.

## 10. 알려진 함정

| 증상 | 원인 | 대응 |
|------|------|------|
| `Could not connect to Blender` | 애드온 미실행 | 사용자에게 Blender + 애드온 활성화 요청 |
| `context is incorrect` | `bpy.ops` 컨텍스트 부재 | `bpy.data` API로 대체하거나 `temp_override` |
| 오브젝트에 `.001` 접미사 | 스크립트 재실행 시 purge 누락 | 스크립트 상단에 `purge(접두사)` 추가 |
| 노면 마킹이 얼룩덜룩 | Z-파이팅 (동일 높이) | 마킹을 Z +0.0005 띄움 |
| 렌더가 응답 없음 | 프레임 수 과다 / Cycles 사용 | EEVEE 사용, 프레임 범위 축소, 백그라운드 렌더 |
| 근접 샷에서 물체가 잘림 | `clip_start` 기본값 0.1m | `clip_start = 0.005` |
| 머티리얼이 전부 회색 | `use_nodes` 미설정 또는 뷰포트가 Solid 셰이딩 | `use_nodes=True` 확인, 뷰포트를 Material Preview로 |
| 스크린샷이 엉뚱한 각도 | 뷰포트가 사용자 시점 | 검증 전 카메라 뷰로 전환하거나 뷰 행렬 지정 |

## 11. 스크린샷 검증 시 뷰 지정

뷰포트 스크린샷은 사용자가 마지막에 보던 각도를 찍는다. 검증에는 재현 가능한 각도가 필요하므로, 촬영 전에 뷰를 명시적으로 맞춘다:

```python
# 트랙 전체 조감 — 검증용 표준 뷰
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        r3d = area.spaces[0].region_3d
        r3d.view_perspective = 'ORTHO'
        r3d.view_rotation = (1.0, 0.0, 0.0, 0.0)   # 톱 뷰
        r3d.view_distance = 6.0
        r3d.view_location = (0.0, 0.0, 0.0)
        break
```

톱 뷰(조감)는 배치·좌표 검증에, 카메라 뷰는 최종 룩 검증에 쓴다. 두 각도를 모두 확인해야 "위에서는 맞는데 옆에서 보니 공중에 떠 있는" 오류를 잡는다.
