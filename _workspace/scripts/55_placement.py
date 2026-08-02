# -*- coding: utf-8 -*-
"""
55_placement.py — 객체 배치 + ArUco 마커 짝 배치 + QR 아군표식 + 체크포인트 3곳 (scene-dresser 산출)

실행 순서(고정): 00 -> 10 -> 20 -> 30 -> 40 -> 50 -> 60 -> 55 -> 70 -> 80 -> 90 -> 95
번호는 55지만 60_markers.py *다음*에 실행한다 — 마커 프로토타입(_PROTO_marker, _PROTO_qr)이 필요하기 때문이다.

spec v1.2.0: objects 배열이 23 -> 24개(참가자 후기 기준 24번째 mortar 추가)로 늘었고,
qr_marker 블록(아군표식 QR 1개)이 새로 생겼다. 객체 개수는 하드코딩하지 않고 spec objects
배열 길이를 그대로 따른다 — 다음에 또 늘어나도 이 파일을 고칠 필요가 없어야 한다.

입력
  - _workspace/spec/track_spec.json 의 objects(가변 길이, v1.2.0 기준 24), checkpoints(3곳),
    markers 블록, qr_marker 블록
  - 50_objects.py 가 만든 _PROTO_{kind} (7종), 60_markers.py 가 만든 _PROTO_marker / _PROTO_qr

출력
  - 04_Objects 컬렉션: OBJ_{id:02d}_{kind_token} (+ 부품)  x len(spec.objects)
  - 05_Markers 컬렉션: ARU_{id:02d} (+ 부품)               x len(spec.objects)
  - 05_Markers 컬렉션: QRM_01 (+ 부품)                     x 0 또는 1 (qr_marker 스펙 유무)
  - 01_Markings 컬렉션: CHK_ALPHA / CHK_BRAVO / CHK_CHARLIE (+ _Decal, _Pin)

핵심 원칙
  - 메시 데이터는 공유한다 (inst.data = proto.data). 완전 복제 금지 — 메모리와
    "프로토타입 수정이 전체에 즉시 반영"되는 이점을 모두 잃는다.
  - Z 는 항상 0. 프로토타입 원점이 바닥에 있으므로 오프셋이 필요 없다. 물체가
    뜨거나 묻히면 배치가 아니라 프로토타입 원점 문제이므로, 여기서 Z 를 임의로
    더해 덮지 않고 asset-modeler 에게 보고한다.
  - yaw 는 스펙 값을 그대로 쓴다. yaw_mode: "tangential" 인 4곳(id 3·7·17·19)도
    마찬가지다 — track-surveyor 가 이미 인접 건물 벽에 대한 접선 방향으로 계산해
    둔 값이다. (역산 확인: id=3 의 경우 near_sector 2 중심에서 객체로의 방사각
    +90'가 스펙 yaw 값과 일치 — 이미 "장축을 벽면과 나란히" 조건을 만족한다.)
    스펙에 yaw 필드가 없을 때만 포지션 id 기반 결정적 폴백을 쓴다.

명명 규약 주의사항 (verify_scene.py 와의 실제 계약)
  scene-qa/scripts/verify_scene.py 의 top_level() 은 이름의 '_' 개수로 대표/부품을
  가린다 (OBJ_ 대표=2개, ARU_/CHK_ 대표=1개). 그런데 kind 문자열 중 "ammo_box" 는
  그 자체에 '_' 가 있어 "OBJ_04_ammo_box" 로 지으면 '_' 가 3개가 되어 대표가 부품으로
  오판되고 개수 검증이 영구히 실패한다. 그래서 오브젝트 *표시 이름*에 넣는 kind 토큰만
  '_' -> '-' 로 치환한다 (_safe_kind_token). 프로토타입 조회('_PROTO_{kind}')는 스펙
  원문 kind 문자열을 그대로 쓴다 — asset-modeler 와의 계약은 그대로 유지된다.
"""

import bpy
import math
import os
from mathutils import Matrix

WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
exec(open(os.path.join(WORKSPACE, "scripts", "00_common.py")).read())

purge("OBJ_")
purge("ARU_")
purge("CHK_")
purge("QRM_")

KIND_NAMES = set(SPEC.get("object_kinds", {}).keys())


# ---------------------------------------------------------------- 이름 헬퍼
def _safe_kind_token(kind):
    """오브젝트 표시 이름에 넣을 kind 토큰. '_' 를 '-' 로 바꿔 verify_scene.py 의
    '_' 개수 기반 대표/부품 판별과의 충돌을 막는다. 자세한 이유는 모듈 docstring 참고."""
    return kind.replace("_", "-")


def _collect_hierarchy(root):
    items = [root]
    for c in root.children:
        items.extend(_collect_hierarchy(c))
    return items


def duplicate_proto_group(proto_name, new_name, col_name):
    """proto_name 오브젝트(+자손 부품)를 메시 공유 복제해 new_name(+동일 접미사)
    인스턴스 그룹을 만든다. 위치/회전은 호출부가 반환된 루트에 설정한다.

    프로토타입이 없으면 (None, []) 를 반환한다 — 호출부가 건너뛰고 계속 진행한다.
    """
    proto_root = bpy.data.objects.get(proto_name)
    if proto_root is None:
        return None, []

    protos = _collect_hierarchy(proto_root)
    mapping = {}
    for p in protos:
        inst = p.copy()
        if p.data is not None:
            inst.data = p.data  # 메시 데이터 공유 (완전 복제 금지)
        suffix = p.name[len(proto_name):]  # '' 또는 '_Barrel' 등 부품 접미사
        inst.name = new_name + suffix
        mapping[p] = inst
        link_to(inst, col_name)

    for p, inst in mapping.items():
        if p.parent is not None and p.parent in mapping:
            inst.parent = mapping[p.parent]
            inst.matrix_parent_inverse = p.matrix_parent_inverse.copy()

    root_inst = mapping[proto_root]
    return root_inst, list(mapping.values())


def _build_checkpoint_pin(name, pin_h, loc, col, mat):
    """체크포인트 위치를 표시하는 부유 핀 — 바닥에서 살짝 뜬 기둥 + 다이아몬드 촉.

    '부유' 는 Z 오프셋으로 만들지 않는다 (배치 원칙 위반). 대신 메시 정점 자체를
    바닥에서 띄운 형태로 만들어, 오브젝트 원점(=CHK 대표의 좌표)은 항상 Z=0 을 유지한다.
    """
    seg = 8
    r_pole = 0.006
    r_base = 0.014
    z0 = pin_h * 0.18   # 바닥에서 뜨는 간격
    z1 = pin_h * 0.70
    z2 = pin_h * 0.86   # 다이아몬드 최대 반경 위치
    z3 = pin_h          # 촉 끝

    verts = []
    for i in range(seg):
        a = 2.0 * math.pi * i / seg
        verts.append((r_pole * math.cos(a), r_pole * math.sin(a), z0))
    for i in range(seg):
        a = 2.0 * math.pi * i / seg
        verts.append((r_pole * math.cos(a), r_pole * math.sin(a), z1))
    for i in range(seg):
        a = 2.0 * math.pi * i / seg
        verts.append((r_base * math.cos(a), r_base * math.sin(a), z2))
    apex_i = len(verts)
    verts.append((0.0, 0.0, z3))
    bottom_i = len(verts)
    verts.append((0.0, 0.0, z0))

    r0, r1, r2 = 0, seg, 2 * seg
    faces = []
    for i in range(seg):
        j = (i + 1) % seg
        faces.append((r0 + i, r0 + j, r1 + j, r1 + i))   # 기둥 옆면
        faces.append((r1 + i, r1 + j, r2 + j, r2 + i))   # 다이아몬드 아랫면
        faces.append((r2 + i, r2 + j, apex_i))           # 다이아몬드 윗면(촉)
        faces.append((r0 + j, r0 + i, bottom_i))         # 기둥 바닥 캡
    return mesh_object(name, verts, faces, loc, col, mat)


def _check_building_clearance(pid, x, y, kind):
    """근처 섹터 풋프린트와 겹치는지 대략적으로 검사한다 (사전 경보용, 정밀 판정은 scene-inspector).

    track-surveyor 가 이미 검증·보정한 객체(near_sector 필드가 있는 기존 포지션들, 필요하면
    moved_mm 로 좌표까지 옮겨 겹침을 해소했다)는 건너뛰고, 아직 그 검증을 안 거친 신규
    포지션(예: spec v1.2.0 의 24번, near_sector 필드 없음)만 대상으로 한다. 겹치더라도
    배치를 멈추지 않고 print 로만 보고한다 — 좌표 조정은 track-surveyor 의 판단 영역이다.
    """
    margin = float(SPEC.get("object_kinds", {}).get(kind, {}).get("r", 0.05))
    for sname, sdata in SPEC.get("sectors", {}).items():
        scx, scy = sdata["pos"][0], sdata["pos"][1]
        hx, hy = sdata.get("half_extent", [0.15, 0.15])
        if abs(x - scx) < (hx + margin) and abs(y - scy) < (hy + margin):
            print("[55_placement] WARNING: OBJ id=%d(kind=%s) @ (%.3f, %.3f) 가 SEC_%s 풋프린트"
                  "(center=%.2f,%.2f half_extent=%.3f,%.3f)와 겹칠 가능성 — 배치는 유지, "
                  "좌표 조정은 track-surveyor 판단 영역이라 여기서 건드리지 않는다"
                  % (pid, kind, x, y, sname, scx, scy, hx, hy))


# ---------------------------------------------------------------- 객체 + 마커 짝 (개수는 spec 을 따른다)
TANGENTIAL_IDS = sorted(o["id"] for o in SPEC.get("objects", []) if o.get("yaw_mode") == "tangential")
print("[55_placement] yaw_mode=tangential 포지션(건물 벽 클리어런스 <0.05m, 스펙 yaw 그대로 사용): %s"
      % TANGENTIAL_IDS)

markers_cfg = SPEC.get("markers", {})
MARKER_OFFSET = markers_cfg.get("offset", 0.04)
# _PROTO_marker 의 로컬 정면이 +X 가 아니면 이 상수로 보정한다 (예: +Y 정면이면 -math.pi/2).
# 스펙의 yaw_convention("+X 축 기준 반시계 헤딩")과 동일 관례를 마커 보드에도 적용한 가정이다.
MARKER_FORWARD_OFFSET = 0.0

# 60_markers.py 계약: 프로토타입은 기본 패턴(ARU_MAT_00)을 달고 있고, 포지션별 실제 패턴은
# ARU_MAT_01 ~ ARU_MAT_{len(spec.objects):02d} 로 이미 만들어져 있다(60 도 spec 을 그대로
# 순회하므로 개수는 항상 여기 n_objects_spec 과 일치한다). 복제 후 슬롯을 갈아끼워야 각
# 마커가 자기 포지션의 코드를 표시한다. 슬롯 인덱스/포맷은 하드코딩하지 않고 프로토타입의
# 커스텀 프로퍼티에서 읽는다.
_MARKER_PROTO = bpy.data.objects.get("_PROTO_marker")
MARKER_SLOT_IDX = _MARKER_PROTO.get("marker_slot") if _MARKER_PROTO is not None else None
if MARKER_SLOT_IDX is not None:
    MARKER_SLOT_IDX = int(MARKER_SLOT_IDX)
MARKER_MAT_FMT = (_MARKER_PROTO.get("marker_mat_fmt") if _MARKER_PROTO is not None else None) or "ARU_MAT_%02d"
if _MARKER_PROTO is not None and MARKER_SLOT_IDX is None:
    print("[55_placement] WARNING: _PROTO_marker 에 marker_slot 커스텀 프로퍼티 없음 — 마커 패턴 슬롯 교체 전부 건너뜀")

n_objects_spec = len(SPEC.get("objects", []))
print("[55_placement] 스펙 objects 배열 길이 %d — 이 값을 그대로 배치 개수 기대값으로 쓴다"
      % n_objects_spec)

missing_kinds = set()
missing_marker = False

for pos in SPEC.get("objects", []):
    pid = pos["id"]
    kind = pos["kind"]
    x, y = pos["pos"][0], pos["pos"][1]
    yaw = pos.get("yaw")
    if yaw is None:
        # 스펙에 yaw 가 없을 때만 쓰는 결정적 폴백 (재실행해도 항상 같은 값)
        yaw = ((pid * 37) % 360) * math.pi / 180.0

    if kind not in KIND_NAMES:
        print("[55_placement] WARNING: id=%d 알 수 없는 kind '%s' — object_kinds 에 없음, 그대로 진행"
              % (pid, kind))

    if "near_sector" not in pos:
        # track-surveyor 가 아직 건물 클리어런스를 검증하지 않은 신규 포지션(spec v1.2.0 의 id=24 등)
        _check_building_clearance(pid, x, y, kind)

    proto_name = "_PROTO_%s" % kind
    new_name = "OBJ_%02d_%s" % (pid, _safe_kind_token(kind))
    root_inst, parts = duplicate_proto_group(proto_name, new_name, "04_Objects")
    if root_inst is None:
        missing_kinds.add(kind)
        print("[55_placement] SKIP: 프로토타입 없음 %s (object id=%d 건너뜀)" % (proto_name, pid))
    else:
        root_inst.location = (x, y, 0.0)            # Z=0 — 프로토타입 원점이 바닥
        root_inst.rotation_euler = (0.0, 0.0, yaw)

    # 대응 ArUco 마커 보드 — marker_dir 방향으로 offset 만큼 떨어진 지점
    mdir = pos.get("marker_dir", [1.0, 0.0])
    mx, my = float(mdir[0]), float(mdir[1])
    mlen = math.hypot(mx, my)
    if mlen < 1e-9:
        mx, my, mlen = 1.0, 0.0, 1.0
    mx, my = mx / mlen, my / mlen
    marker_x, marker_y = x + mx * MARKER_OFFSET, y + my * MARKER_OFFSET
    marker_yaw = math.atan2(my, mx) + MARKER_FORWARD_OFFSET

    aru_root, aru_parts = duplicate_proto_group("_PROTO_marker", "ARU_%02d" % pid, "05_Markers")
    if aru_root is None:
        missing_marker = True
        print("[55_placement] SKIP: 마커 프로토타입 없음 _PROTO_marker (object id=%d 마커 건너뜀)" % pid)
    else:
        aru_root.location = (marker_x, marker_y, 0.0)
        aru_root.rotation_euler = (0.0, 0.0, marker_yaw)

        # 포지션별 마커 패턴 슬롯 교체 (60_markers.py 계약). link='OBJECT' 를 먼저 하지 않으면
        # 공유 메시 데이터의 슬롯을 덮어써 인스턴스 전부가 마지막 값으로 바뀐다.
        if MARKER_SLOT_IDX is None:
            pass  # 위에서 이미 한 번 경고했다
        elif not (0 <= MARKER_SLOT_IDX < len(aru_root.material_slots)):
            print("[55_placement] WARNING: marker_slot 인덱스 %s 범위 밖 (슬롯 %d개, object id=%d) — 교체 건너뜀"
                  % (MARKER_SLOT_IDX, len(aru_root.material_slots), pid))
        else:
            mat_name = MARKER_MAT_FMT % pid
            mat = bpy.data.materials.get(mat_name)
            if mat is None:
                print("[55_placement] WARNING: 머티리얼 %s 없음(60_markers.py 미실행?) — id=%d 슬롯 교체 건너뜀, 기본 패턴 유지"
                      % (mat_name, pid))
            else:
                slot = aru_root.material_slots[MARKER_SLOT_IDX]
                slot.link = 'OBJECT'
                slot.material = mat

if missing_kinds:
    print("[55_placement] WARNING: 누락된 객체 프로토타입 종류: %s — 50_objects.py 확인"
          % sorted(missing_kinds))
if missing_marker:
    print("[55_placement] WARNING: _PROTO_marker 없음 — 60_markers.py 확인")


# ---------------------------------------------------------------- QR 아군표식 (spec v1.2.0 신규)
# ArUco 마커와 동일한 방식(메시 공유 복제 + marker_slot 커스텀 프로퍼티로 오브젝트-레벨
# 머티리얼 슬롯 교체)이다. 다만 QR 은 객체 옆이 아니라 spec.qr_marker 의 절대 좌표에
# 그 자체로 서므로 marker_dir/offset 계산이 없다.
qr_cfg = SPEC.get("qr_marker")
made_qr_expected = 0
made_qr = 0

if qr_cfg is None:
    print("[55_placement] INFO: qr_marker 스펙 없음 — QR 아군표식 배치 건너뜀")
else:
    made_qr_expected = 1
    qx, qy = qr_cfg["pos"][0], qr_cfg["pos"][1]
    qyaw = qr_cfg.get("yaw", 0.0)
    qr_pattern_id = qr_cfg.get("pattern_id", 0)

    _QR_PROTO = bpy.data.objects.get("_PROTO_qr")
    if _QR_PROTO is None:
        print("[55_placement] SKIP: _PROTO_qr 없음(60_markers.py 미실행?) — QR 아군표식 배치 건너뜀, 나머지는 계속 진행")
    else:
        qr_root, qr_parts = duplicate_proto_group("_PROTO_qr", "QRM_01", "05_Markers")
        if qr_root is None:
            print("[55_placement] SKIP: QRM_01 복제 실패 — _PROTO_qr 확인")
        else:
            qr_root.location = (qx, qy, 0.0)          # Z=0 — 프로토타입 원점이 바닥
            qr_root.rotation_euler = (0.0, 0.0, qyaw)
            made_qr = 1

            qr_slot_idx = _QR_PROTO.get("marker_slot")
            if qr_slot_idx is None:
                print("[55_placement] WARNING: _PROTO_qr 에 marker_slot 커스텀 프로퍼티 없음 — "
                      "QR 패턴 슬롯 교체 건너뜀, 배치 자체는 유지")
            else:
                qr_slot_idx = int(qr_slot_idx)
                qr_mat_fmt = _QR_PROTO.get("marker_mat_fmt") or "QR_MAT_%02d"
                if not (0 <= qr_slot_idx < len(qr_root.material_slots)):
                    print("[55_placement] WARNING: QR marker_slot 인덱스 %d 범위 밖 (슬롯 %d개) — 교체 건너뜀"
                          % (qr_slot_idx, len(qr_root.material_slots)))
                else:
                    qr_mat_name = qr_mat_fmt % qr_pattern_id
                    qr_mat = bpy.data.materials.get(qr_mat_name)
                    if qr_mat is None:
                        print("[55_placement] WARNING: 머티리얼 %s 없음(60_markers.py 미실행?) — "
                              "QR 슬롯 교체 건너뜀, 기본 패턴 유지" % qr_mat_name)
                    else:
                        qr_slot = qr_root.material_slots[qr_slot_idx]
                        qr_slot.link = 'OBJECT'
                        qr_slot.material = qr_mat


# ---------------------------------------------------------------- 체크포인트 3곳
CHK_COLLECTION = "01_Markings"  # 노면 표식 성격이 강해 마킹 계열에 둔다 (purge/조회는 이름 접두사 기준이라 무관)

expected_cp = SPEC.get("checkpoints", {})
if len(expected_cp) != 3:
    print("[55_placement] WARNING: 스펙 checkpoints 개수 %d (기대 3)" % len(expected_cp))

for name in CP_ORDER:
    data = expected_cp.get(name)
    if data is None:
        print("[55_placement] WARNING: 체크포인트 %s 스펙 없음 — 건너뜀" % name)
        continue

    x, y = data["pos"][0], data["pos"][1]
    color = data.get("color", [0.8, 0.8, 0.8])
    decal_r = data.get("decal_r", 0.09)
    pin_h = data.get("pin_h", 0.12)

    chk = bpy.data.objects.new("CHK_%s" % name, None)
    chk.empty_display_type = 'PLAIN_AXES'
    chk.empty_display_size = 0.05
    chk.location = (x, y, 0.0)                      # 대표 좌표 — 스펙과 대조되는 지점
    link_to(chk, CHK_COLLECTION)
    # matrix_world 는 depsgraph 갱신 전까지 갱신되지 않을 수 있어, 순수 이동행렬을 직접 구성한다
    parent_inv = Matrix.Translation((-x, -y, 0.0))

    decal_mat = get_or_create_material("MAT_CHK_%s_decal" % name, color=color, roughness=0.6, metallic=0.0)
    decal = make_disc("CHK_%s_Decal" % name, decal_r, loc=(x, y, LINE_Z), seg=32,
                       col=CHK_COLLECTION, mat=decal_mat)
    decal.parent = chk
    decal.matrix_parent_inverse = parent_inv

    pin_mat = get_or_create_material("MAT_CHK_%s_pin" % name, color=color, roughness=0.25,
                                      emission=color, emission_strength=1.4)
    pin = _build_checkpoint_pin("CHK_%s_Pin" % name, pin_h, loc=(x, y, 0.0),
                                 col=CHK_COLLECTION, mat=pin_mat)
    add_bevel(pin, width=0.0007, segments=2)
    pin.parent = chk
    pin.matrix_parent_inverse = parent_inv

    print("[55_placement] 체크포인트 %s @ (%.2f, %.2f) decal_r=%.3f pin_h=%.3f"
          % (name, x, y, decal_r, pin_h))


# ---------------------------------------------------------------- 개수 검산
# verify_scene.py 의 top_level() 과 동일한 방식(대표='_' 개수)으로 세어 결과가 일치하게 한다.
def _reps(prefix, depth):
    return [o for o in bpy.data.objects if o.name.startswith(prefix) and o.name.count("_") == depth]


made_objects = len(_reps("OBJ_", 2))
made_markers = len(_reps("ARU_", 1))
made_qr_markers = len(_reps("QRM_", 1))
made_checkpoints = len(_reps("CHK_", 1))

print("[55_placement] objects=%d (spec=%d) markers=%d (spec=%d) qr_markers=%d (spec=%d) "
      "checkpoints=%d (expected 3)"
      % (made_objects, n_objects_spec, made_markers, n_objects_spec,
         made_qr_markers, made_qr_expected, made_checkpoints))
if made_objects != n_objects_spec:
    print("[55_placement] WARNING: 개수 불일치 — 스펙 objects 배열 길이(%d) 확인, 루프에서 예외가 조용히 삼켜졌을 수 있다"
          % n_objects_spec)
if made_markers != n_objects_spec:
    print("[55_placement] WARNING: 마커 개수 불일치 — _PROTO_marker 및 offset/marker_dir 확인")
if made_qr_markers != made_qr_expected:
    print("[55_placement] WARNING: QR 마커 개수 불일치(만든 개수=%d, 기대=%d) — _PROTO_qr / qr_marker 스펙 확인"
          % (made_qr_markers, made_qr_expected))
if made_checkpoints != 3:
    print("[55_placement] WARNING: 체크포인트 개수 불일치 — SPEC checkpoints 확인")
