"""MediaPipe CPU关键点 + 几何/时序规则的问题说明；不调用视觉大模型。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

RULE_VERSION = "sanda-feedback-mediapipe-2026-09-18-v2"
ACTIONS = {
    "stance": "实战式",
    "straight_combo": "前后手直拳组合",
    "hook_combo": "前后手摆拳组合",
    "front_straight": "前手直拳", "rear_straight": "后手直拳",
    "front_hook": "前手摆拳", "rear_hook": "后手摆拳",
    "front_low_kick": "前低鞭腿", "rear_low_kick": "后低鞭腿",
}
STANCES = {"left": "左式（左手、左脚在前）", "right": "右式（右手、右脚在前）"}
PHASES = {"start": "开始实战式", "motion": "动作过程", "finish": "动作结束瞬间", "end": "结束实战式"}
STATE_LABELS = {"candidate": "待教师确认", "not_observed": "已检查帧中未发现", "unable": "证据不足", "pending_rule": "待规则/测量确认"}
DOC = "武术散打得分点.docx 表1"
SUMMARY = "扣分点说明功能需求汇总.md"
# code -> 问题、身体部位（相对于前后侧）、标准、不能自动判定的原因。
RULES = {
    "stance_elbow": ("前手肘角不在90°～135°", "front_arm", "前手大小臂夹角90°～135°", ""),
    "stance_height": ("前手拳峰未与鼻尖同高", "front_hand", "拳峰与鼻尖同高，允许±3 cm", "缺少真实长度标定，不能把画面比例当作厘米"),
    "stance_rear_guard": ("后手未夹紧并贴近肋骨与下颚", "rear_arm", "后手大小臂夹紧、紧贴肋骨与下颚", ""),
    "stance_knee": ("单腿或双腿伸直", "knees", "两膝微屈", ""),
    "stance_width": ("两脚站距过宽或过窄", "feet", "两脚略与肩同宽，允许±10 cm", "缺少真实长度标定，不能把画面比例当作厘米"),
    "stance_toes": ("两脚内八或外八", "feet", "两脚大致平行、朝斜前方", ""),
    "stance_torso": ("躯干正向前方", "torso", "躯干侧向前方", ""),
    "stance_head": ("挺胸抬头", "head_torso", "下颚微收、含胸收腹", "Pose33不足以可靠判定含胸收腹，需教师查看"),
    "guard_low": ("向下掉手", "hand", "护手保持在下颚附近", ""),
    "guard_back": ("向后拉手", "hand", "护手保持原护位，不向后拉", ""),
    "guard_elbow": ("向上抬肘", "arm", "护手侧保持护位，不向上抬肘", ""),
    "vertical_fist": ("出拳成立拳", "hand", "前手直拳出拳结束时拳背朝上", "轻量Pose关键点不能可靠判断握拳朝向，需教师查看"),
    "shoulder_level": ("出拳未与肩部齐平", "arm", "出拳与肩部齐平", ""),
    "guard_recover": ("未回收护住下颚", "hand", "前手回收护住下颚", ""),
    "foot_flexed": ("脚背未绷直（勾脚尖）", "foot", "低鞭腿脚背绷直", ""),
    "hip_turn": ("未翻胯", "hip", "低鞭腿翻胯", ""),
    "arm_swing": ("未顺势向下甩手", "arm", "踢腿同侧手顺势向下甩手", ""),
}
STANCE_RULES = tuple(code for code in RULES if code.startswith("stance_"))
PARTS = {"arm": "臂肘", "hand": "手", "foot": "脚背", "hip": "髋", "knees": "双膝", "feet": "双脚", "torso": "躯干", "head_torso": "头部与胸腹"}


def build_checks(action: str, stance: str) -> list[dict[str, Any]]:
    if not isinstance(action, str) or not isinstance(stance, str) or action not in ACTIONS or stance not in STANCES:
        raise ValueError("请选择支持的动作和左式/右式")
    checks: list[dict[str, Any]] = []

    def add(code: str, segment: str, phase: str, role: str = "", blocked: str = "", source: str = SUMMARY):
        name, part, standard, reason = RULES[code]
        if part.startswith(("front_", "rear_")):
            role, part = part.split("_", 1)
        side = ("左" if stance == "left" else "右") if role == "front" else ("右" if stance == "left" else "左") if role == "rear" else ""
        prefix = "前侧" if role == "front" else "后侧" if role == "rear" else ""
        checks.append({"id": f"{segment}:{phase}:{role}:{code}", "code": code,
                       "name": name, "bodyPart": f"{prefix}{PARTS[part]}" + (f"（{side}）" if side else ""),
                       "segment": segment, "segmentLabel": ACTIONS[segment], "phase": phase,
                       "phaseLabel": PHASES[phase], "standard": standard,
                       "source": source, "blockedReason": blocked or reason, "role": role})

    for code in STANCE_RULES:
        add(code, "stance", "start", source=f"{DOC} 第3～9行")
    segments = {"straight_combo": ["front_straight", "rear_straight"],
                "hook_combo": ["front_hook", "rear_hook"]}.get(action, [action])
    for segment in segments:
        if segment == "stance":
            continue
        front = segment.startswith("front_")
        role = "front" if front else "rear"
        guard = "rear" if front else "front"
        hook = "hook" in segment
        kick = "kick" in segment
        source = f"{DOC} 第{10 if front else 11}行" if "straight" in segment else SUMMARY
        for phase in ("motion", "finish"):
            if not kick or front:
                for code in ("guard_low", "guard_back", "guard_elbow"):
                    # 后手摆拳前手回收未包含向后拉手，不扩展问卷清单。
                    if segment == "rear_hook" and code == "guard_back":
                        continue
                    blocked = "原文摆拳阶段误写为直拳，需教师核对" if segment == "front_hook" else ""
                    if hook and code == "guard_elbow":
                        blocked = "摆拳要求抬肘与错误抬肘的幅度/阶段需区分"
                    add(code, segment, phase, guard, blocked, source)
            if segment in {"rear_straight", "rear_hook"}:
                for code in ("guard_low", "guard_back", "guard_elbow"):
                    add(code, segment, phase, "rear", "需确认出拳侧掉手/拉手/抬肘的阶段边界", SUMMARY)
            if segment == "rear_hook" or segment == "rear_low_kick":
                add("guard_recover", segment, phase, "front")
            if kick:
                for code in ("foot_flexed", "hip_turn", "arm_swing"):
                    add(code, segment, phase, role)
            elif phase == "finish" or front:
                add("shoulder_level", segment, phase, role,
                    "原文摆拳阶段误写为直拳，需教师核对" if hook else "")
            if segment == "front_straight" and phase == "finish":
                add("vertical_fist", segment, phase, "front", source=source)
    for code in STANCE_RULES:
        add(code, "stance", "end", source=f"{DOC} 第12～18行")
    # 保持开始→前手→后手→结束，再按各阶段身体部位排列；不统计重复次数。
    order = {name: i + 1 for i, name in enumerate(segments)}
    checks.sort(key=lambda c: (0 if c["phase"] == "start" else 99 if c["phase"] == "end" else order[c["segment"]],
                               list(PHASES).index(c["phase"]), c["bodyPart"], c["id"]))
    return checks


def analyze_feedback(action: str, stance: str, front: Path | None, side: Path | None,
                     *, stopped: Callable[[], bool] = lambda: False, config=None, pipeline_factory=None) -> dict:
    from core.feedback_geometry import analyze_geometry
    return analyze_geometry(action, stance, front, side, stopped=stopped,
                            config=config, pipeline_factory=pipeline_factory)


def format_report(record: dict) -> str:
    result = record["result"]
    method = "MediaPipe关键点规则检查；二维投影与工程阈值仍需教师标定，不作为正式成绩。" if result.get("backend") == "mediapipe" else "旧版结果；可重新分析生成MediaPipe规则检查结果。"
    lines = ["散打动作问题说明（不打分）", f"学生：{record['studentId']} {record['studentName']}",
             f"动作：{ACTIONS[result['action']]}；{STANCES[result['stance']]}",
             f"记录时间：{record['createdAt']}；保存至：{record['expiresAt']}",
             f"规则版本：{result['ruleVersion']}", method, "", result["summary"], "", "动作问题："]
    issues = [c for c in result["checks"] if c["status"] == "candidate" and c["review"] != "revoked"]
    for i, c in enumerate(issues, 1):
        state = "教师已确认" if c["review"] == "confirmed" else "待教师确认"
        lines.append(f"{i}. {c['segmentLabel']} / {c['phaseLabel']} / {c['bodyPart']}：{c['name']}（{state}）")
    if not issues:
        lines.append("当前没有未撤销的候选问题；不代表所有项目均合格。")
    incomplete = [c for c in result["checks"] if c["status"] in {"unable", "pending_rule"}]
    if incomplete:
        lines += ["", "未完成判断的项目："]
        for c in incomplete:
            lines.append(f"- {c['segmentLabel']} / {c['phaseLabel']} / {c['bodyPart']}：{c['name']}；{c['reason']}")
    if result["needsRerecord"]:
        lines += ["", "请重新录制：全身及拳脚入画、光线充足、减少遮挡，保留开始和结束实战式。"]
    return "\n".join(lines) + "\n"
