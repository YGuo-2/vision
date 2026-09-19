"""学生练习的 MediaPipe Lite CPU 推理及确定性几何规则。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from core.paths import models_dir
from core.pose_features import derive_valid_mask
from core.rule_scoring import _angle_deg, _rule_feet_parallel, _rule_knee_slight_bend
from core.vision_pipeline import MediaPipePipeline, PipelineConfig


@dataclass(frozen=True)
class FeedbackConfig:
    """工程初始阈值，保留标定入口；除肘角范围外不冒充教师确认的标准。"""
    sample_fps: float = 12.0
    max_edge: int = 640
    min_valid: int = 3
    valid_ratio: float = .6
    trigger_ratio: float = .3
    motion_distance: float = .25  # 相对躯干长度
    guard_drop: float = .25
    guard_back: float = .18
    shoulder_height: float = .20
    elbow_raise: float = .10
    torso_front_ratio: float = .75
    foot_angle: float = 145.0
    hip_rotation: float = 20.0

    def __post_init__(self):
        if any(not math.isfinite(v) or v <= 0 for v in asdict(self).values()):
            raise ValueError("规则参数必须是有限正数")
        if self.sample_fps > 60 or self.max_edge < 64 or self.min_valid < 2 or not isinstance(self.min_valid, int):
            raise ValueError("采样频率应不超过60，分辨率至少64，有效帧数至少2")
        if self.valid_ratio > 1 or self.trigger_ratio > 1:
            raise ValueError("比例参数不能大于1")


def _pipeline():
    directory = models_dir()
    if not (directory / "pose_landmarker_lite.task").is_file():
        raise FileNotFoundError("缺少 MediaPipe Lite，请退出学生练习，在设置的模型管理中安装 lite。")
    return MediaPipePipeline(models_dir=directory, cfg=PipelineConfig(
        pose_variant="lite", enable_hands=False, delegate="cpu", running_mode="video"))


def extract_series(path: Path, cfg: FeedbackConfig, stopped: Callable[[], bool], pipeline_factory=None) -> dict:
    """顺序解码、降采样推理；只保留关键点。丢失帧全无效，绝不复用上一帧。"""
    cap = cv2.VideoCapture(str(path))
    pipe = None
    try:
        if not cap.isOpened():
            raise ValueError(f"视频无法读取，请重新录制：{path.name}")
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("视频帧率不可用，请重新录制")
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        total = int(total) if math.isfinite(total) else 0
        stride = max(1, math.ceil(fps / cfg.sample_fps))
        points, frames, times = [], [], []
        index = 0
        timestamp = -1
        while cap.grab():
            if stopped():
                raise InterruptedError("分析已取消")
            if index % stride == 0 or index == total - 1:
                ok, frame = cap.retrieve()
                if not ok or frame is None:
                    raise ValueError("视频存在不可解码的帧，请重新录制")
                h, w = frame.shape[:2]
                if max(h, w) > cfg.max_edge:
                    scale = cfg.max_edge / max(h, w)
                    frame = cv2.resize(frame, (max(1, round(w * scale)), max(1, round(h * scale))))
                if pipe is None:
                    pipe = (pipeline_factory or _pipeline)()
                timestamp = max(timestamp + 1, round(index * 1000 / fps))
                landmarks, _ = pipe.infer(frame, timestamp_ms=timestamp)
                arr = np.zeros((33, 4), dtype=np.float32)
                if landmarks is not None:
                    for j, lm in enumerate(landmarks[:33]):
                        # x和z统一为图像高度单位，防止非正方形画面把角度算歪。
                        arr[j] = (lm.x * w / h, lm.y, lm.z * w / h, getattr(lm, "visibility", 0))
                points.append(arr)
                frames.append(index)
                times.append(index / fps)
            index += 1
        if not points:
            raise ValueError("视频没有可读取的帧，请重新录制")
        lm = np.stack(points)
        mask = derive_valid_mask(lm) & np.isfinite(lm[:, :, :3]).all(axis=2)
        return {"landmarks": lm, "valid_mask": mask, "frames": frames, "times": times}
    finally:
        cap.release()
        if pipe is not None:
            pipe.close()


def _torso(lm):
    return np.linalg.norm((lm[:, 11, :2] + lm[:, 12, :2] - lm[:, 23, :2] - lm[:, 24, :2]) / 2, axis=1)


def _indices(role, stance):
    left = (stance == "left") == (role != "rear")
    return (11, 13, 15, 23, 25, 27, 29, 31) if left else (12, 14, 16, 24, 26, 28, 30, 32)


def phase_windows(series: dict, action: str, stance: str, cfg: FeedbackConfig) -> dict:
    """用肢体相对躯干的离开/回收划分阶段，不把录像机械对半切割。"""
    lm, mask = series["landmarks"], series["valid_mask"]
    n, edge = len(lm), cfg.min_valid
    windows = {}
    if n < edge * 2 + 1:
        return windows
    torso = _torso(lm)
    for phase, indices in (("start", np.arange(edge)), ("end", np.arange(n - edge, n))):
        if mask[indices][:, [11, 12, 15, 16, 23, 24]].all() and np.all(torso[indices] > 1e-4):
            wrists = (lm[indices][:, [15, 16], :2] - lm[indices][:, [11, 12], :2]) / torso[indices, None, None]
            if np.max(np.linalg.norm(wrists - np.median(wrists, axis=0), axis=2)) <= cfg.motion_distance / 2:
                windows[("stance", phase)] = indices
    segments = {"straight_combo": ["front_straight", "rear_straight"],
                "hook_combo": ["front_hook", "rear_hook"]}.get(action, [] if action == "stance" else [action])
    events = []
    for segment in segments:
        role = "front" if segment.startswith("front_") else "rear"
        sh, el, wr, hip, knee, ankle, heel, toe = _indices(role, stance)
        anchor, moving = (hip, ankle) if "kick" in segment else (sh, wr)
        valid = mask[:, [anchor, moving, 11, 12, 23, 24]].all(axis=1) & (torso > 1e-4)
        if not valid[:edge].all():
            continue
        relative = (lm[:, moving, :2] - lm[:, anchor, :2]) / np.maximum(torso[:, None], 1e-4)
        baseline = np.median(relative[:edge], axis=0)
        distance = np.linalg.norm(relative - baseline, axis=1)
        if np.max(distance[:edge]) > cfg.motion_distance / 2:
            continue
        active = valid & (distance > cfg.motion_distance)
        boundaries = np.flatnonzero(np.diff(np.r_[False, active, False]))
        candidates = []
        for start, end in zip(boundaries[::2], boundaries[1::2]):
            # 遮挡导致的断点不能当作完整动作；必须观察到离开和回收。
            if end - start < edge or start == 0 or end >= n or not valid[start - 1] or not valid[end]:
                continue
            peak = start + int(np.argmax(distance[start:end]))
            candidates.append((start, peak, end))
        # ponytail: 一段每侧只接受一个清晰动作；多次/重叠无法分段时提示重录，后续再做动作模板分段。
        if len(candidates) == 1:
            events.append((segment, candidates[0]))
    if len(events) != len(segments) or any(a[1][1] >= b[1][1] for a, b in zip(events, events[1:])):
        return windows
    for segment, (start, peak, end) in events:
        windows[(segment, "motion")] = np.arange(start, end)
        windows[(segment, "finish")] = np.arange(max(start, peak - 1), min(end, peak + 2))
    return windows


def _measure(check: dict, lm: np.ndarray, mask: np.ndarray, baseline: np.ndarray, baseline_mask: np.ndarray,
             stance: str, cfg: FeedbackConfig):
    code = check["code"]
    sh, el, wr, hip, knee, ankle, heel, toe = _indices(check["role"], stance)
    torso = _torso(lm)
    required = [11, 12, 23, 24]
    if code == "stance_knee":
        bad, valid, _ = _rule_knee_slight_bend(lm, mask)
        for a, b in ((23, 25), (25, 27), (24, 26), (26, 28)):
            valid &= np.linalg.norm(lm[:, a, :2] - lm[:, b, :2], axis=1) > 1e-4
        return bad, valid
    if code == "stance_toes":
        bad, valid, _ = _rule_feet_parallel(lm, mask)
        valid &= (np.linalg.norm(lm[:, 31, :2] - lm[:, 29, :2], axis=1) > 1e-4)
        valid &= (np.linalg.norm(lm[:, 32, :2] - lm[:, 30, :2], axis=1) > 1e-4)
        return bad, valid
    if code == "stance_elbow":
        required += [sh, el, wr]
        angles = np.array([_angle_deg(p[sh, :2], p[el, :2], p[wr, :2]) for p in lm])
        bad = (angles < 90) | (angles > 135)
        mask = mask.copy()
        mask[:, el] &= (np.linalg.norm(lm[:, sh, :2] - lm[:, el, :2], axis=1) > 1e-4)
        mask[:, wr] &= (np.linalg.norm(lm[:, wr, :2] - lm[:, el, :2], axis=1) > 1e-4)
    elif code in {"stance_rear_guard", "guard_low", "guard_recover"}:
        required += [wr, 9, 10]
        mouth = (lm[:, 9, :2] + lm[:, 10, :2]) / 2
        if code == "guard_low":
            bad = lm[:, wr, 1] - mouth[:, 1] > cfg.guard_drop * torso
        else:
            bad = np.linalg.norm(lm[:, wr, :2] - mouth, axis=1) > (.45 if code == "stance_rear_guard" else .6) * torso
            if code == "stance_rear_guard":
                required.append(el)
                center = (lm[:, 11, :2] + lm[:, 12, :2] + lm[:, 23, :2] + lm[:, 24, :2]) / 4
                bad |= np.linalg.norm(lm[:, el, :2] - center, axis=1) > .5 * torso
    elif code in {"guard_elbow", "shoulder_level"}:
        joint = el if code == "guard_elbow" else wr
        required += [sh, joint]
        bad = (lm[:, sh, 1] - lm[:, el, 1] > cfg.elbow_raise * torso) if code == "guard_elbow" else (np.abs(lm[:, wr, 1] - lm[:, sh, 1]) > cfg.shoulder_height * torso)
    elif code == "stance_torso":
        bad = np.linalg.norm(lm[:, 11, :2] - lm[:, 12, :2], axis=1) > cfg.torso_front_ratio * torso
    elif code == "foot_flexed":
        required += [knee, ankle, toe]
        angles = np.array([_angle_deg(p[knee, :2], p[ankle, :2], p[toe, :2]) for p in lm])
        bad = angles < cfg.foot_angle
        mask = mask.copy()
        mask[:, toe] &= np.linalg.norm(lm[:, toe, :2] - lm[:, ankle, :2], axis=1) > 1e-4
    elif code in {"guard_back", "arm_swing", "hip_turn"}:
        required += [wr, sh, 0] if code == "guard_back" else [wr, sh] if code == "arm_swing" else []
        if not baseline_mask[:, required].all() or np.any(_torso(baseline) < 1e-4):
            return np.zeros(len(lm), bool), np.zeros(len(lm), bool)
        if code == "hip_turn":
            axis = lm[:, 24, [0, 2]] - lm[:, 23, [0, 2]]
            initial = baseline[:, 24, [0, 2]] - baseline[:, 23, [0, 2]]
            base_angle = math.atan2(float(np.median(initial[:, 1])), float(np.median(initial[:, 0])))
            delta = (np.arctan2(axis[:, 1], axis[:, 0]) - base_angle + np.pi) % (2 * np.pi) - np.pi
            bad = np.abs(np.degrees(delta)) < cfg.hip_rotation
        elif code == "arm_swing":
            initial = np.median((baseline[:, wr, 1] - baseline[:, sh, 1]) / _torso(baseline))
            bad = (lm[:, wr, 1] - lm[:, sh, 1]) / np.maximum(torso, 1e-4) - initial < cfg.motion_distance
        else:
            direction = np.median(baseline[:, 0, 0] - (baseline[:, 23, 0] + baseline[:, 24, 0]) / 2)
            if abs(direction) < .1 * np.median(_torso(baseline)):
                return np.zeros(len(lm), bool), np.zeros(len(lm), bool)
            initial = np.median((baseline[:, wr, 0] - baseline[:, sh, 0]) / _torso(baseline))
            change = ((lm[:, wr, 0] - lm[:, sh, 0]) / np.maximum(torso, 1e-4) - initial) * np.sign(direction)
            bad = change < -cfg.guard_back
    else:
        return np.zeros(len(lm), bool), np.zeros(len(lm), bool)
    return bad, mask[:, required].all(axis=1) & (torso > 1e-4)


def evaluate_series(action: str, stance: str, views: dict, cfg: FeedbackConfig = FeedbackConfig()) -> dict:
    from core.action_feedback import build_checks, RULE_VERSION

    checks = build_checks(action, stance)
    windows = {view: phase_windows(s, action, stance, cfg) for view, s in views.items()}
    evidence = {}
    for c in checks:
        c.update(status="unable", reason="关键点、视角或动作阶段不足，请重新录制", evidence=[], review="pending")
        if c["blockedReason"]:
            c.update(status="pending_rule", reason=c["blockedReason"])
            continue
        required_view = {"guard_back": "side", "foot_flexed": "side", "stance_toes": "front",
                         "stance_torso": "front", "hip_turn": "front"}.get(c["code"])
        outcomes = []
        for view, series in views.items():
            if required_view and view != required_view:
                continue
            indices = windows[view].get((c["segment"], c["phase"]))
            if indices is None or len(indices) < cfg.min_valid:
                continue
            bad, valid = _measure(c, series["landmarks"][indices], series["valid_mask"][indices],
                series["landmarks"][:cfg.min_valid], series["valid_mask"][:cfg.min_valid], stance, cfg)
            count = int(valid.sum())
            if count < cfg.min_valid or count / len(indices) < cfg.valid_ratio:
                continue
            violation = float((bad & valid).sum() / count)
            # “未做某动作”只能在整个阶段均未出现该动作时成立。
            issue = bool(bad[valid].all()) if c["code"] in {"hip_turn", "arm_swing"} else violation >= cfg.trigger_ratio
            outcomes.append((issue, view, indices, bad, valid, violation))
        if not outcomes:
            continue
        # 多机位判断冲突时不投票猜测，显式保留为无法判断。
        if len({o[0] for o in outcomes}) > 1:
            c["reason"] = "正侧视角规则判断不一致，请检查机位并重新录制或由教师复核"
            continue
        issue = outcomes[0][0]
        c.update(status="candidate" if issue else "not_observed", reason="", measurements=[])
        for _, view, indices, bad, valid, ratio in outcomes:
            series = views[view]
            c["measurements"].append({"view": view, "validFrames": int(valid.sum()), "violationRatio": ratio})
            for index in indices[valid & bad if issue else valid]:
                ref = f"{view}:{series['frames'][index]}"
                evidence[ref] = {"id": ref, "view": view, "frame": series["frames"][index], "timeSeconds": series["times"][index]}
                c["evidence"].append(ref)
    unable = any(c["status"] == "unable" for c in checks)
    issues = any(c["status"] == "candidate" for c in checks)
    return {"schemaVersion": 1, "ruleVersion": RULE_VERSION, "action": action, "stance": stance,
            "backend": "mediapipe", "poseVariant": "lite", "delegate": "cpu", "actionSource": "user_selected",
            "config": asdict(cfg), "status": "partial" if any(c["status"] in {"unable", "pending_rule"} for c in checks) else "completed",
            "needsRerecord": unable, "scoreAuthorized": False, "calibrationStatus": "unvalidated",
            "summary": "规则检查发现待教师确认的问题" if issues else "证据不足，请重新录制" if unable else "已检查项目未发现明显问题，不代表全部项目合格",
            "checks": checks, "evidence": list(evidence.values()), "reviewHistory": []}


def analyze_geometry(action, stance, front, side, *, stopped=lambda: False, config=None, pipeline_factory=None):
    from core.action_feedback import build_checks
    build_checks(action, stance)
    cfg = config or FeedbackConfig()
    views = {}
    for view, path in (("front", front), ("side", side)):
        if stopped():
            raise InterruptedError("分析已取消")
        if path is not None:
            views[view] = extract_series(Path(path), cfg, stopped, pipeline_factory)
    if stopped():
        raise InterruptedError("分析已取消")
    return evaluate_series(action, stance, views, cfg)
