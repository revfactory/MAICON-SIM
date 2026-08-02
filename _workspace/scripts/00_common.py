# -*- coding: utf-8 -*-
"""
00_common.py — MAICON 시뮬레이터 공통 기반 (track-surveyor 산출)

다른 모든 빌드 스크립트가 맨 위에서 이 파일을 exec 으로 로드한다:

    import bpy, os
    WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
    exec(open(os.path.join(WORKSPACE, "scripts", "00_common.py")).read())

따라서 이 파일의 모든 이름은 **모듈 최상위**에 있어야 한다. 함수를 클래스나
if __name__ 블록 안에 숨기면 exec 된 네임스페이스에서 보이지 않는다.

좌표는 여기에 하드코딩하지 않는다. 단일 진실 공급원은 spec/track_spec.json 이고
이 파일은 그것을 읽기만 한다. 좌표를 고칠 때는 JSON 만 고치고 스크립트를 재실행한다.

--------------------------------------------------------------------------
제공 API
--------------------------------------------------------------------------
  SPEC                                  track_spec.json 을 로드한 딕셔너리
  WORKSPACE / SPEC_PATH / OUTPUT_DIR    경로 상수
  ROOT_COLLECTION / COLLECTIONS         컬렉션 계층 이름

  setup_scene(remove_defaults=True)     미터 단위 + 컬렉션 계층 생성
  purge(prefix)                         접두사 오브젝트 제거 (멱등성)
  get_or_create_material(name, ...)     이름 기반 머티리얼 재사용
  link_collection(name, parent=...)     컬렉션 생성/조회 후 반환
  link_to(obj, col_name)                오브젝트를 지정 컬렉션에만 연결

  make_box(name, size, loc, ...)        원점이 바닥인 박스      (정점 z: 0~h)
  make_cylinder(name, r, h, loc, seg)   원점이 바닥인 원통      (정점 z: 0~h)
  make_cone(name, r, h, loc, seg)       원점이 바닥인 원뿔      (정점 z: 0~h)
  make_plane(name, w, h, z, loc)        XY 평면 (오브젝트 z=z, 정점 z=0)
  make_disc(name, r, loc, seg, ...)     원판 (center_z<0 이면 오목 — 포트홀용)

  mesh_object(name, verts, faces, ...)  from_pydata 저수준 래퍼
  add_bevel(obj, width, segments)       베벨 모디파이어
  set_material(obj, mat)                머티리얼 할당
  rgba(c, a=1.0)                        [r,g,b] -> (r,g,b,a)
  path_xy() / path_tagged(tag)          SPEC["path"] 접근 헬퍼
  obj_by_id(i) / sector(n) / cp(name)   SPEC 접근 헬퍼

원점을 바닥에 두는 이유: 원점이 중심이면 배치할 때마다 높이의 절반을 더해야 하고,
그 계산 실수가 "물체가 땅에 반쯤 묻힘"의 주원인이다. 배치 코드는 항상 z=0 을 쓴다.
"""

import bpy
import bmesh  # noqa: F401  (하위 스크립트가 쓸 수 있게 미리 로드)
import json
import math
import os

# ---------------------------------------------------------------- 경로 상수
WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
PROJECT = os.path.dirname(WORKSPACE)
SPEC_PATH = os.path.join(WORKSPACE, "spec", "track_spec.json")
SCRIPTS_DIR = os.path.join(WORKSPACE, "scripts")
QA_DIR = os.path.join(WORKSPACE, "qa")
OUTPUT_DIR = os.path.join(PROJECT, "output")
STILLS_DIR = os.path.join(OUTPUT_DIR, "stills")

# ---------------------------------------------------------------- SPEC 로드
if not os.path.exists(SPEC_PATH):
    raise RuntimeError(
        "track_spec.json 이 없다: %s\n"
        "track-surveyor 가 스펙을 먼저 산출해야 한다." % SPEC_PATH
    )

with open(SPEC_PATH, "r", encoding="utf-8") as _fp:
    SPEC = json.load(_fp)

# 자주 쓰는 파생 상수 (SPEC 을 대체하지 않는다 — 편의용 뷰)
ARENA_W = SPEC["arena"]["w"]
ARENA_H = SPEC["arena"]["h"]
LINE_Z = SPEC["road"]["line_z"]
OBJ_BY_ID = {o["id"]: o for o in SPEC["objects"]}
CP_ORDER = ["ALPHA", "BRAVO", "CHARLIE"]

# ---------------------------------------------------------------- 컬렉션 계층
ROOT_COLLECTION = "MAICON"
COLLECTIONS = [
    "00_Ground",    # GND_*
    "01_Markings",  # MRK_*
    "02_Hazards",   # HZD_*
    "03_Sectors",   # SEC_*
    "04_Objects",   # OBJ_*
    "05_Markers",   # ARU_*
    "06_Vehicle",   # UGV_*
    "07_Cameras",   # CAM_*
    "08_Lights",    # LGT_*
]
PREFIX_OF = {
    "00_Ground": "GND_", "01_Markings": "MRK_", "02_Hazards": "HZD_",
    "03_Sectors": "SEC_", "04_Objects": "OBJ_", "05_Markers": "ARU_",
    "06_Vehicle": "UGV_", "07_Cameras": "CAM_", "08_Lights": "LGT_",
}


# ---------------------------------------------------------------- 컬렉션
def link_collection(name, parent=ROOT_COLLECTION):
    """컬렉션을 생성하거나 조회해 반환한다. parent 아래에 붙인다(멱등)."""
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)

    scene_root = bpy.context.scene.collection

    if name == parent:  # 루트 자신
        if col.name not in scene_root.children:
            scene_root.children.link(col)
        return col

    root = link_collection(parent, parent)
    if col.name not in root.children:
        # 다른 부모에 붙어 있으면 떼어낸다 (중복 링크 방지)
        for c in bpy.data.collections:
            if c is not col and col.name in c.children:
                c.children.unlink(col)
        if col.name in scene_root.children:
            scene_root.children.unlink(col)
        root.children.link(col)
    return col


def link_to(obj, col_name):
    """오브젝트를 지정 컬렉션에만 연결한다 (기존 링크는 모두 해제)."""
    col = col_name if isinstance(col_name, bpy.types.Collection) else link_collection(col_name)
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)
    return obj


# ---------------------------------------------------------------- 멱등성
def purge(prefix):
    """이 접두사로 시작하는 오브젝트를 모두 제거해 스크립트 재실행을 안전하게 만든다.

    purge 를 빼먹으면 재실행 때 Blender 가 .001 접미사 오브젝트를 쌓고,
    그 이름 충돌이 이후 모든 이름 참조를 조용히 깨뜨린다.
    """
    n = 0
    for o in [o for o in bpy.data.objects if o.name.startswith(prefix)]:
        bpy.data.objects.remove(o, do_unlink=True)
        n += 1
    for m in [m for m in bpy.data.meshes if m.users == 0]:
        bpy.data.meshes.remove(m)
    for c in [c for c in bpy.data.curves if c.users == 0]:
        bpy.data.curves.remove(c)
    return n


def get_or_create_material(name, color=None, roughness=None, metallic=None,
                           emission=None, emission_strength=None):
    """이름으로 머티리얼을 재사용한다. 지우고 다시 만들면 다른 스크립트의 참조가 끊긴다.

    color 등을 넘기면 호출할 때마다 값을 다시 설정한다 (재실행 시 색 수정 반영).
    """
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = None
    for nd in mat.node_tree.nodes:
        if nd.type == 'BSDF_PRINCIPLED':
            bsdf = nd
            break
    if bsdf is not None:
        _set_input(bsdf, "Base Color", rgba(color) if color is not None else None)
        _set_input(bsdf, "Roughness", roughness)
        _set_input(bsdf, "Metallic", metallic)
        if emission is not None:
            # Blender 4.x: "Emission Color" / 3.x: "Emission"
            _set_input(bsdf, "Emission Color", rgba(emission))
            _set_input(bsdf, "Emission", rgba(emission))
        _set_input(bsdf, "Emission Strength", emission_strength)
        if color is not None:
            mat.diffuse_color = rgba(color)  # 솔리드 뷰포트 표시용
    return mat


def _set_input(node, key, value):
    if value is None or key not in node.inputs:
        return
    try:
        node.inputs[key].default_value = value
    except (TypeError, ValueError):
        pass


def set_material(obj, mat):
    """머티리얼(또는 이름)을 오브젝트에 할당한다."""
    if isinstance(mat, str):
        mat = get_or_create_material(mat)
    if obj.data is None:
        return obj
    if len(obj.data.materials):
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    return obj


def rgba(c, a=1.0):
    """[r,g,b] 또는 (r,g,b,a) 를 Blender 가 받는 4요소 튜플로 정규화."""
    if c is None:
        return None
    c = tuple(c)
    return c if len(c) == 4 else (c[0], c[1], c[2], a)


# ---------------------------------------------------------------- 지오메트리
def _v3(loc):
    """(x, y) 또는 (x, y, z) 를 3요소 튜플로."""
    if loc is None:
        return (0.0, 0.0, 0.0)
    loc = tuple(loc)
    return (loc[0], loc[1], loc[2] if len(loc) > 2 else 0.0)


def mesh_object(name, verts, faces, loc=(0, 0, 0), col=None, mat=None):
    """bpy.data + from_pydata 로 메시 오브젝트를 만든다 (bpy.ops 미사용).

    bpy.ops 는 화면 컨텍스트에 의존해 MCP 실행 시 실패하거나 엉뚱한 오브젝트에 적용된다.
    """
    me = bpy.data.meshes.new(name + "_mesh")
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.validate(verbose=False)
    me.update()
    for p in me.polygons:
        p.use_smooth = False
    ob = bpy.data.objects.new(name, me)
    ob.location = _v3(loc)
    link_to(ob, col if col is not None else ROOT_COLLECTION)
    if mat is not None:
        set_material(ob, mat)
    return ob


def make_box(name, size, loc=(0, 0, 0), col=None, mat=None):
    """원점이 바닥 중앙인 박스. size=(w, d, h) → 정점 z 범위 0~h.

    XY 는 중심 정렬, Z 만 0 에서 위로 자란다. 따라서 노면 배치는 z=0 그대로 쓴다.
    """
    w, d, h = float(size[0]), float(size[1]), float(size[2])
    hw, hd = w * 0.5, d * 0.5
    verts = [(-hw, -hd, 0.0), (hw, -hd, 0.0), (hw, hd, 0.0), (-hw, hd, 0.0),
             (-hw, -hd, h),   (hw, -hd, h),   (hw, hd, h),   (-hw, hd, h)]
    faces = [(0, 3, 2, 1),          # bottom (-Z)
             (4, 5, 6, 7),          # top    (+Z)
             (0, 1, 5, 4),          # -Y
             (1, 2, 6, 5),          # +X
             (2, 3, 7, 6),          # +Y
             (3, 0, 4, 7)]          # -X
    return mesh_object(name, verts, faces, loc, col, mat)


def make_cylinder(name, r, h, loc=(0, 0, 0), seg=24, col=None, mat=None):
    """원점이 바닥 중앙인 원통. 정점 z 범위 0~h."""
    r, h, seg = float(r), float(h), max(3, int(seg))
    verts = []
    for i in range(seg):
        a = 2.0 * math.pi * i / seg
        verts.append((r * math.cos(a), r * math.sin(a), 0.0))
    for i in range(seg):
        a = 2.0 * math.pi * i / seg
        verts.append((r * math.cos(a), r * math.sin(a), h))
    faces = []
    for i in range(seg):
        j = (i + 1) % seg
        faces.append((i, j, seg + j, seg + i))
    faces.append(tuple(range(seg - 1, -1, -1)))        # bottom (-Z)
    faces.append(tuple(range(seg, 2 * seg)))           # top    (+Z)
    return mesh_object(name, verts, faces, loc, col, mat)


def make_cone(name, r, h, loc=(0, 0, 0), seg=16, col=None, mat=None):
    """원점이 바닥 중앙인 원뿔 (미사일 노즈 등). 정점 z 범위 0~h."""
    r, h, seg = float(r), float(h), max(3, int(seg))
    verts = []
    for i in range(seg):
        a = 2.0 * math.pi * i / seg
        verts.append((r * math.cos(a), r * math.sin(a), 0.0))
    verts.append((0.0, 0.0, h))
    apex = seg
    faces = [(i, (i + 1) % seg, apex) for i in range(seg)]
    faces.append(tuple(range(seg - 1, -1, -1)))        # bottom (-Z)
    return mesh_object(name, verts, faces, loc, col, mat)


def make_plane(name, w, h, z=0.0, loc=(0.0, 0.0), col=None, mat=None):
    """XY 평면. 정점은 로컬 z=0, 오브젝트 원점이 z 높이에 놓인다.

    노면 마킹은 z=SPEC["road"]["line_z"](0.5 mm)로 띄운다. 같은 높이면 Z-파이팅이 난다.
    """
    w, h = float(w), float(h)
    hw, hh = w * 0.5, h * 0.5
    verts = [(-hw, -hh, 0.0), (hw, -hh, 0.0), (hw, hh, 0.0), (-hw, hh, 0.0)]
    faces = [(0, 1, 2, 3)]
    return mesh_object(name, verts, faces, (loc[0], loc[1], z), col, mat)


def make_disc(name, r, loc=(0, 0, 0), seg=24, center_z=0.0, col=None, mat=None):
    """원판. center_z 를 음수로 주면 중심이 내려가 오목해진다 (포트홀).

    주의: 오목 원판만은 정점 z 범위가 center_z~0 이다. 다른 make_* 의 0~h 규칙과 다르며,
    이는 노면을 '파낸' 형태를 표현하기 위한 의도적 예외다.
    """
    r, seg = float(r), max(3, int(seg))
    verts = [(0.0, 0.0, float(center_z))]
    for i in range(seg):
        a = 2.0 * math.pi * i / seg
        verts.append((r * math.cos(a), r * math.sin(a), 0.0))
    faces = [(0, 1 + i, 1 + (i + 1) % seg) for i in range(seg)]
    return mesh_object(name, verts, faces, loc, col, mat)


def add_bevel(obj, width=0.0008, segments=2, angle=0.523):
    """하드서피스 에셋의 필수 마감. 완벽한 직각 모서리는 빛을 받지 않아 CG처럼 보인다."""
    for m in list(obj.modifiers):          # 순회 중 삭제하면 항목을 건너뛴다
        if m.type == 'BEVEL':
            obj.modifiers.remove(m)
    bev = obj.modifiers.new("Bevel", 'BEVEL')
    bev.width = width
    bev.segments = segments
    bev.limit_method = 'ANGLE'
    bev.angle_limit = angle
    return bev


# ---------------------------------------------------------------- SPEC 접근
def sector(n):
    return SPEC["sectors"][str(n)]


def cp(name):
    return SPEC["checkpoints"][name]


def obj_by_id(i):
    return OBJ_BY_ID[i]


def path_xy():
    """주행 경로 제어점을 [(x, y), ...] 로 반환."""
    return [(p["pos"][0], p["pos"][1]) for p in SPEC["path"]]


def path_tagged(tag):
    """tag(START/ALPHA/BRAVO/CHARLIE/FINISH)에 해당하는 제어점 인덱스와 좌표."""
    for i, p in enumerate(SPEC["path"]):
        if p.get("tag") == tag:
            return i, (p["pos"][0], p["pos"][1])
    return None, None


# ---------------------------------------------------------------- 씬 초기화
def setup_scene(remove_defaults=True):
    """미터 실측 스케일 + 컬렉션 계층. 몇 번 호출해도 결과가 같다(멱등).

    5 m x 3.5 m 를 그대로 Blender 단위(1 unit = 1 m)로 쓴다. 축소 스케일을 쓰면
    이후 모든 좌표 계산에 환산이 끼어들어 실수를 부른다.
    """
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = 'METERS'

    if remove_defaults:
        for nm in ("Cube", "Camera", "Light"):
            o = bpy.data.objects.get(nm)
            if o is not None:
                bpy.data.objects.remove(o, do_unlink=True)

    link_collection(ROOT_COLLECTION)
    for name in COLLECTIONS:
        link_collection(name)

    for d in (QA_DIR, OUTPUT_DIR, STILLS_DIR):
        if not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
    return bpy.data.collections[ROOT_COLLECTION]


# exec 로 로드될 때마다 실행 — 컬렉션 계층이 항상 존재함을 보장한다.
setup_scene()

print("[00_common] SPEC v%s loaded | objects=%d sectors=%d path=%d | collections=%d"
      % (SPEC["_meta"]["version"], len(SPEC["objects"]), len(SPEC["sectors"]),
         len(SPEC["path"]), len(COLLECTIONS)))
