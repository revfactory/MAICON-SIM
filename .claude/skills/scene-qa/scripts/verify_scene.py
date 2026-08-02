# -*- coding: utf-8 -*-
"""
MAICON 씬 자동 검수 — Blender 내부에서 exec으로 실행한다.

    exec(open("/Users/robin/Downloads/maicon-sim/.claude/skills/scene-qa/scripts/verify_scene.py").read())

track_spec.json과 실제 씬 상태를 대조하고, 결과를 표준 출력 + JSON 파일로 남긴다.
검수관(scene-inspector)이 매번 검증 코드를 새로 작성하지 않게 하는 것이 목적이다.

이 스크립트는 씬을 수정하지 않는다 (프레임 위치만 원복하고 종료).
"""

import bpy
import json
import os
from mathutils import Vector

WORKSPACE = "/Users/robin/Downloads/maicon-sim/_workspace"
SPEC_PATH = os.path.join(WORKSPACE, "spec", "track_spec.json")
TIMELINE_PATH = os.path.join(WORKSPACE, "spec", "timeline.json")
OUT_PATH = os.path.join(WORKSPACE, "qa", "verify_result.json")

ARENA_W, ARENA_H = 5.0, 3.5
POS_TOL = 0.001          # 좌표 허용 오차 1 mm
GROUND_TOL = 0.005       # 노면 부유 허용 5 mm
# 개수 기대값은 스펙에서 읽는다. 하드코딩하면 스펙이 바뀔 때마다 검수가 거짓 실패를 낸다.
# (객체 수는 명세 개정으로 실제로 23 → 24 로 바뀐 전례가 있다.)
EXPECTED = {"objects": 23, "potholes": 2, "barriers": 2, "sectors": 9, "checkpoints": 3}

report = {"passed": [], "failed": [], "unverified": [], "info": {}}


def ok(msg):
    report["passed"].append(msg)


def bad(msg, hint=""):
    report["failed"].append({"issue": msg, "hint": hint})


def skip(msg):
    report["unverified"].append(msg)


def world_bbox(obj):
    """월드 좌표 기준 바운딩박스 (min, max). 메시가 없으면 None."""
    if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'FONT'}:
        return None
    mw = obj.matrix_world
    cs = [mw @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(c.x for c in cs), min(c.y for c in cs), min(c.z for c in cs)))
    hi = Vector((max(c.x for c in cs), max(c.y for c in cs), max(c.z for c in cs)))
    return lo, hi


def by_prefix(p):
    return [o for o in bpy.data.objects if o.name.startswith(p)]


# ---------------------------------------------------------------- 스펙 로드
spec = None
if os.path.exists(SPEC_PATH):
    try:
        with open(SPEC_PATH, encoding="utf-8") as f:
            spec = json.load(f)
        ok("track_spec.json 로드")
        # 스펙에 실제로 들어 있는 개수를 기대값으로 삼는다
        for k in ("objects", "potholes", "barriers"):
            if isinstance(spec.get(k), list):
                EXPECTED[k] = len(spec[k])
        if isinstance(spec.get("sectors"), dict):
            EXPECTED["sectors"] = len(spec["sectors"])
        if isinstance(spec.get("checkpoints"), dict):
            EXPECTED["checkpoints"] = len(spec["checkpoints"])
    except Exception as e:
        bad("track_spec.json 파싱 실패: %s" % e, "JSON 문법 확인")
else:
    skip("track_spec.json 없음 — 좌표 대조 생략 (track-surveyor 미실행?)")


# ---------------------------------------------------------------- 이름 충돌
dupes = [o.name for o in bpy.data.objects if "." in o.name and o.name.split(".")[-1].isdigit()]
if dupes:
    bad("이름 충돌 오브젝트 %d개: %s" % (len(dupes), dupes[:8]),
        "스크립트 상단 purge() 누락. 해당 스크립트에 purge(접두사) 추가 후 재실행")
else:
    ok("이름 충돌 없음 (.001 접미사 부재)")


# ---------------------------------------------------------------- 경기장 치수
base = bpy.data.objects.get("GND_Base")
if base:
    d = base.dimensions
    if abs(d.x - ARENA_W) < 0.01 and abs(d.y - ARENA_H) < 0.01:
        ok("경기장 치수 %.3f x %.3f m" % (d.x, d.y))
    else:
        bad("경기장 치수 불일치: %.3f x %.3f (기대 %.1f x %.1f)" % (d.x, d.y, ARENA_W, ARENA_H),
            "단위 혼동(mm↔m) 의심. 10_ground.py 확인")
else:
    skip("GND_Base 없음 — 10_ground.py 미실행")


# ---------------------------------------------------------------- 개수 검증
def top_level(prefix, depth):
    """부품을 제외한 대표 오브젝트만 센다.
    두 조건을 함께 쓴다:
      - parent is None : 부품은 대표의 자식이므로 제외된다 (가장 견고한 기준)
      - '_' 개수 == depth : 부모 없이 만들어진 부품에 대한 2차 방어

    주의: kind 토큰에 '_'가 들어가면 이 판별이 깨진다. ammo_box를 그대로 쓰면
    OBJ_04_ammo_box의 '_'가 3개가 되어 대표가 부품으로 오판된다.
    배치 스크립트는 표시 이름에서만 kind의 '_'를 '-'로 치환한다 (OBJ_04_ammo-box).
    프로토타입 조회는 스펙 원문(_PROTO_ammo_box)을 그대로 쓰므로 계약은 유지된다."""
    return [o for o in by_prefix(prefix)
            if o.parent is None and o.name.count("_") == depth]


counts = {
    "objects": len(top_level("OBJ_", 2)),
    "potholes": len(by_prefix("HZD_Pothole")),
    "barriers": len(by_prefix("HZD_Barrier")),
    "sectors": len(set(o.name[:6] for o in by_prefix("SEC_"))),
    "checkpoints": len(top_level("CHK_", 1)),
}
report["info"]["counts"] = counts
for k, want in EXPECTED.items():
    got = counts.get(k, 0)
    if got == want:
        ok("%s 개수 %d개" % (k, got))
    elif got == 0:
        skip("%s 미생성 (해당 단계 미실행)" % k)
    else:
        bad("%s 개수 불일치: %d개 (기대 %d개)" % (k, got, want),
            "루프에서 예외가 조용히 삼켜졌는지 확인")


# ---------------------------------------------------------------- 좌표 대조
def check_pos(name, want_xy, label):
    obj = bpy.data.objects.get(name)
    if obj is None:
        skip("%s 오브젝트 없음 (%s)" % (name, label))
        return
    dx = abs(obj.location.x - want_xy[0])
    dy = abs(obj.location.y - want_xy[1])
    if dx < POS_TOL and dy < POS_TOL:
        ok("%s 좌표 일치 (%.3f, %.3f)" % (label, want_xy[0], want_xy[1]))
    else:
        # Y 부호만 뒤집으면 맞는 경우 = 축 반전
        flip = abs(obj.location.y + want_xy[1]) < POS_TOL and dx < POS_TOL
        bad("%s 좌표 불일치: 스펙 (%.3f, %.3f) ↔ 실제 (%.3f, %.3f)"
            % (label, want_xy[0], want_xy[1], obj.location.x, obj.location.y),
            "Y축 부호 반전 의심 — 픽셀→월드 변환식 확인" if flip else "스펙/스크립트 양쪽 확인")


if spec:
    for cid, cp in (spec.get("checkpoints") or {}).items():
        check_pos("CHK_%s" % cid, cp["pos"], "체크포인트 %s" % cid)
    # 섹터의 스펙 좌표는 main+annex 합성 풋프린트의 중심이며, 그 값을 그대로 갖는 것은
    # _Base다. _Main은 합성 중심에서 벗어나 있으므로 대조 기준이 될 수 없다.
    for sid, sc in (spec.get("sectors") or {}).items():
        nm = "SEC_%02d_Base" % int(sid)
        if bpy.data.objects.get(nm):
            check_pos(nm, sc["pos"], "SECTOR %s" % sid)
    for pos in (spec.get("objects") or []):
        matches = [o for o in bpy.data.objects if o.name.startswith("OBJ_%02d_" % pos["id"])]
        if matches:
            check_pos(matches[0].name, pos["pos"], "객체 포지션 %d" % pos["id"])


# ---------------------------------------------------------------- 경계 이탈 / 노면 정합
outside, floating, buried = [], [], []
for o in bpy.data.objects:
    if o.name.startswith(("CAM_", "LGT_", "PATH_", "_PROTO_")) or o.type == 'EMPTY':
        continue
    bb = world_bbox(o)
    if bb is None:
        continue
    lo, hi = bb
    # 경기장 밖에 있는 것이 정상인 부류:
    #   GND_Frame/GND_Under — 주행면을 감싸는 테두리 (안쪽이면 하단 주행선 침범)
    #   ENV_*               — 경기장이 놓인 방의 바닥·벽·천장·조명
    if not o.name.startswith(("GND_", "ENV_")) and (
            lo.x < -ARENA_W / 2 - 0.01 or hi.x > ARENA_W / 2 + 0.01 or
            lo.y < -ARENA_H / 2 - 0.01 or hi.y > ARENA_H / 2 + 0.01):
        outside.append(o.name)
    # 노면에 직접 놓이는 것만 Z 검사한다. 건물은 기단(_Base)만 노면에 닿고
    # 타워·부속동·창문은 기단 위에 얹히므로 검사 대상이 아니다 — 포함시키면
    # 정상적으로 떠 있는 부품이 전부 "부유" 오탐을 낸다.
    on_ground = (o.name.startswith(("OBJ_", "ARU_", "HZD_Barrier"))
                 or o.name.endswith("_Base"))
    if o.parent is None and on_ground:
        if lo.z > GROUND_TOL:
            floating.append((o.name, round(lo.z, 4)))
        elif lo.z < -GROUND_TOL:
            buried.append((o.name, round(lo.z, 4)))

if outside:
    bad("경기장 경계 이탈 %d개: %s" % (len(outside), outside[:8]), "좌표 스케일 또는 부호 오류")
else:
    ok("모든 오브젝트가 경기장 안에 있음")

if floating:
    bad("노면에서 뜬 오브젝트 %d개: %s" % (len(floating), floating[:8]),
        "오브젝트 원점이 중심에 있는데 Z=0으로 배치했을 가능성. 원점을 바닥으로")
elif buried:
    bad("노면에 묻힌 오브젝트 %d개: %s" % (len(buried), buried[:8]), "Z 오프셋 확인")
else:
    ok("노면 정합 양호 (묻힘/부유 없음)")


# ---------------------------------------------------------------- 마킹 Z-파이팅
mrk_bad = []
for o in by_prefix("MRK_"):
    bb = world_bbox(o)
    if bb and not (0.0003 <= bb[0].z <= 0.0008):
        mrk_bad.append((o.name, round(bb[0].z, 5)))
if mrk_bad:
    bad("마킹 Z 이상 %d개: %s" % (len(mrk_bad), mrk_bad[:8]),
        "노면과 같은 높이면 Z-파이팅. Z를 0.0005로")
elif by_prefix("MRK_"):
    ok("마킹 Z 오프셋 정상 (Z-파이팅 없음)")


# ---------------------------------------------------------------- 머티리얼 미할당
nomat = [o.name for o in bpy.data.objects
         if o.type == 'MESH' and len(o.material_slots) == 0
         and not o.name.startswith("_PROTO_")]
if nomat:
    bad("머티리얼 미할당 %d개: %s" % (len(nomat), nomat[:8]), "렌더에서 기본 회색으로 보인다")
else:
    ok("모든 메시에 머티리얼 할당됨")


# ---------------------------------------------------------------- 객체 겹침
def overlaps(a, b, margin=0.0):
    la, ha = a
    lb, hb = b
    return (la.x < hb.x - margin and ha.x > lb.x + margin and
            la.y < hb.y - margin and ha.y > lb.y + margin)


tops = [o for o in bpy.data.objects
        if o.name.startswith(("OBJ_", "SEC_")) and o.parent is None]
boxes = [(o.name, world_bbox(o)) for o in tops]
boxes = [(n, b) for n, b in boxes if b]
hits = []
for i in range(len(boxes)):
    for j in range(i + 1, len(boxes)):
        if boxes[i][0][:6] == boxes[j][0][:6]:
            continue  # 같은 섹터의 부속동은 인접이 정상
        if overlaps(boxes[i][1], boxes[j][1], margin=0.002):
            hits.append((boxes[i][0], boxes[j][0]))
if hits:
    bad("바운딩박스 겹침 %d쌍: %s" % (len(hits), hits[:6]), "배치 좌표 재확인")
elif boxes:
    ok("객체/건물 겹침 없음")


# ---------------------------------------------------------------- 애니메이션
root = bpy.data.objects.get("UGV_Root")
if root is None:
    skip("UGV_Root 없음 — 70_vehicle.py 미실행")
elif root.animation_data is None and not root.constraints:
    # 차량은 있으나 애니메이션이 아직 걸리지 않은 상태. 결함이 아니라 미실행이다.
    skip("UGV 애니메이션 없음 — 80_motion.py 미실행")
else:
    scene = bpy.context.scene
    saved = scene.frame_current
    step = max(1, (scene.frame_end - scene.frame_start) // 30)
    traj = []
    for f in range(scene.frame_start, scene.frame_end + 1, step):
        scene.frame_set(f)
        p = root.matrix_world.translation
        traj.append((f, p.x, p.y, p.z))
    scene.frame_set(saved)

    span = max(abs(traj[-1][1] - traj[0][1]), abs(traj[-1][2] - traj[0][2]))
    if span < 0.05:
        bad("차량이 움직이지 않음 (이동량 %.4f m)" % span,
            "Follow Path 타깃 또는 eval_time 키프레임 확인")
    else:
        ok("차량 이동 확인 (총 변위 %.2f m)" % span)

        # 단조 진행 — 누적 이동거리가 줄어드는 구간이 있으면 후진
        segs = [((traj[i + 1][1] - traj[i][1]) ** 2 + (traj[i + 1][2] - traj[i][2]) ** 2) ** 0.5
                for i in range(len(traj) - 1)]
        stalls = [traj[i][0] for i, s in enumerate(segs) if s < 1e-5]
        if stalls:
            bad("정지 구간 프레임 %s" % stalls[:6], "eval_time 키 역전 또는 중복 의심")
        else:
            ok("주행이 단조 진행 (정지·후진 없음)")

        zs = [t[3] for t in traj]
        if max(zs) - min(zs) > 0.02:
            bad("차량 Z 변동 과다 (%.3f m)" % (max(zs) - min(zs)), "경로 Z 또는 커브 tilt 확인")
        else:
            ok("차량 높이 일정")

        # 체크포인트 / 포트홀 근접 거리
        if spec:
            for cid, cp in (spec.get("checkpoints") or {}).items():
                dmin = min(((t[1] - cp["pos"][0]) ** 2 + (t[2] - cp["pos"][1]) ** 2) ** 0.5
                           for t in traj)
                if dmin <= 0.05 + step * 0.01:
                    ok("체크포인트 %s 통과 (최근접 %.3f m)" % (cid, dmin))
                else:
                    bad("체크포인트 %s 미통과 (최근접 %.3f m)" % (cid, dmin),
                        "경로 제어점에 체크포인트 좌표 포함 필요")
            for k, ph in enumerate(spec.get("potholes") or []):
                dmin = min(((t[1] - ph["pos"][0]) ** 2 + (t[2] - ph["pos"][1]) ** 2) ** 0.5
                           for t in traj)
                need = ph.get("r", 0.11) + 0.085
                if dmin >= need:
                    ok("포트홀 %d 회피 (최근접 %.3f m)" % (k + 1, dmin))
                else:
                    bad("포트홀 %d 근접 %.3f m (필요 %.3f m)" % (k + 1, dmin, need),
                        "우회 제어점 2개 삽입")
    report["info"]["trajectory_samples"] = len(traj)


# ---------------------------------------------------------------- 카메라
cams = by_prefix("CAM_")
if not cams:
    skip("카메라 없음 — 90_camera.py 미실행")
else:
    bad_clip = [c.name for c in cams if c.type == 'CAMERA' and c.data.clip_start > 0.01]
    if bad_clip:
        bad("clip_start 과다: %s" % bad_clip, "실측 스케일에서는 0.005 권장 (근접 샷 잘림)")
    else:
        ok("카메라 clip_start 정상 (%d대)" % len([c for c in cams if c.type == 'CAMERA']))

    markers = sorted(bpy.context.scene.timeline_markers, key=lambda m: m.frame)
    bound = [m for m in markers if m.camera]
    if bound:
        shorts = [(bound[i].frame, bound[i + 1].frame - bound[i].frame)
                  for i in range(len(bound) - 1)
                  if bound[i + 1].frame - bound[i].frame < 40]
        if shorts:
            bad("컷 길이 40프레임 미만: %s" % shorts, "시청자가 인식하기 전에 넘어간다")
        else:
            ok("컷 %d개, 모두 40프레임 이상" % len(bound))
    else:
        skip("카메라 바인딩 마커 없음 — 컷 편집 미구성")


# ---------------------------------------------------------------- 출력
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("=" * 60)
print("MAICON 씬 검수 결과")
print("=" * 60)
print("통과 %d / 실패 %d / 미검증 %d" %
      (len(report["passed"]), len(report["failed"]), len(report["unverified"])))
if report["failed"]:
    print("\n[실패]")
    for f_ in report["failed"]:
        print("  - %s" % f_["issue"])
        if f_["hint"]:
            print("      → %s" % f_["hint"])
if report["unverified"]:
    print("\n[미검증]")
    for u in report["unverified"]:
        print("  - %s" % u)
print("\n상세: %s" % OUT_PATH)
print("=" * 60)
