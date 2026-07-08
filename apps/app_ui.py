from __future__ import annotations

import csv
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from tkinter import BooleanVar, Canvas, DoubleVar, IntVar, Scrollbar, StringVar, Text, Tk, Toplevel, filedialog, messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

from core.action_compare import compare_video_to_template, create_template_from_video
from analysis.tech_eval import evaluate_video_assets, evaluate_video_detail, export_debug_video, to_jsonable
from core.vision_pipeline import MediaPipePipeline, PipelineConfig
from core.paths import models_dir, outputs_dir
from core import model_manager
from core.parallel_pose_engine import ParallelPoseEngine, default_pipeline_factory
from core.recording_controller import RecordingController, RecordingState
from apps.camera_enum import CameraEntry, InputSourceState, enumerate_cameras, open_camera


ACTION_LABELS_ZH = {
    "V_SIGN": "✌（V 手势）",
    "HANDS_UP": "双手举起",
    "LEFT_HAND_UP": "左手举起",
    "RIGHT_HAND_UP": "右手举起",
    "SQUAT": "下蹲",
}


# Record_Toggle 三态按钮文本映射，供录制回调（任务 7.1/7.2/7.3）与 UI 重构（任务 9.x）复用。
RECORD_BTN_TEXT = {
    "idle": "开始录制",
    "recording": "暂停录制",
    "paused": "继续录制",
}

# 第二摄像头下拉的「不选」sentinel（双摄像头双面视图，issue #57）。
NO_SECOND_CAMERA = "无（单摄像头）"


def clamp_workers(n: int) -> int:
    """将离线线程数钳制到闭区间 [1, os.cpu_count()]。

    - 小于 1 的输入钳制为 1
    - 大于主机 CPU 逻辑核心数的输入钳制为核心数
    - 当 ``os.cpu_count()`` 返回 None（无法确定核心数）时，上界回退为 1

    Validates: Requirements 7.2
    """
    cpu = os.cpu_count()
    upper = cpu if cpu and cpu >= 1 else 1
    try:
        value = int(n)
    except (TypeError, ValueError):
        value = 1
    if value < 1:
        return 1
    if value > upper:
        return upper
    return value


class CollapsibleSection:
    """A collapsible section with a toggle header."""

    def __init__(self, parent: ttk.Frame, title: str, expanded: bool = False) -> None:
        self.parent = parent
        self._expanded = BooleanVar(value=expanded)

        self.header = ttk.Frame(parent)
        self._toggle_btn = ttk.Button(
            self.header,
            text=self._get_toggle_text(),
            command=self._toggle,
            width=len(title) + 4,
        )
        self._toggle_btn.pack(side="left", anchor="w")

        self.content = ttk.Frame(parent)
        if expanded:
            self.content.pack(fill="x", pady=(4, 0))

    def _get_toggle_text(self) -> str:
        arrow = "▾" if self._expanded.get() else "▸"
        return f"{arrow} {self._toggle_btn.cget('text').lstrip('▸▾ ') if hasattr(self, '_toggle_btn') else ''}"

    def _toggle(self) -> None:
        self._expanded.set(not self._expanded.get())
        current_text = self._toggle_btn.cget("text")
        base_text = current_text.lstrip("▸▾ ")
        arrow = "▾" if self._expanded.get() else "▸"
        self._toggle_btn.configure(text=f"{arrow} {base_text}")

        if self._expanded.get():
            self.content.pack(fill="x", pady=(4, 0))
        else:
            self.content.pack_forget()

    def set_title(self, title: str) -> None:
        arrow = "▾" if self._expanded.get() else "▸"
        self._toggle_btn.configure(text=f"{arrow} {title}", width=len(title) + 4)

    def pack_header(self, **kwargs) -> None:
        self.header.pack(**kwargs)

    def is_expanded(self) -> bool:
        return self._expanded.get()


class CompareWindow:
    def __init__(self, parent: Tk) -> None:
        self._win = Toplevel(parent)
        self._win.title("动作分析（模板比对 + 直拳技术评估）")
        self._win.geometry("720x860")
        self._win.minsize(640, 720)

        # Template mode: "existing" or "generate"
        self.template_mode_var = StringVar(value="existing")
        self.base_video_var = StringVar(value="")
        self.template_var = StringVar(value="")
        self.target_video_var = StringVar(value="")

        self.pose_var = StringVar(value="heavy")
        self.workers_var = IntVar(value=1)
        self.start_var = StringVar(value="")
        self.end_var = StringVar(value="")

        self.save_preview_var = BooleanVar(value=True)
        self.preview_out_var = StringVar(value="")

        # 模板比对开关：勾选才跑模板相似度匹配（需要模板）；不勾选则仅做直拳技术评估。
        self.do_compare_var = BooleanVar(value=True)
        # 直拳技术评估开关与参数（由原 TechEvalWindow 融合而来，针对单视频）。
        self.do_tech_var = BooleanVar(value=True)
        self.stance_var = StringVar(value="left")
        self.view_var = StringVar(value="auto")
        self.debug_video_var = BooleanVar(value=False)

        self.status_var = StringVar(value="就绪")
        self.result_var = StringVar(value="")
        self.progress_text_var = StringVar(value="")
        # 直拳技术指标明细文本框（懒创建于 _build）。
        self.detail_text: Text | None = None

        # Store last comparison result for display
        self._last_score: float | None = None
        self._last_match_info: str = ""

        self._stop_evt = threading.Event()
        self._worker: threading.Thread | None = None

        self._build()
        self._win.protocol("WM_DELETE_WINDOW", self._on_close)

    def is_open(self) -> bool:
        return bool(self._win.winfo_exists())

    def focus(self) -> None:
        try:
            self._win.deiconify()
            self._win.lift()
            self._win.focus_force()
        except Exception:
            pass

    def _build(self) -> None:
        outer = ttk.Frame(self._win, padding=12)
        outer.pack(fill="both", expand=True)

        # ===== Step 1: Template Preparation（可选，仅模板比对需要）=====
        step1 = ttk.Labelframe(outer, text="① 准备模板（仅模板比对需要）", padding=10)
        step1.pack(fill="x")

        # 启用模板比对开关：关闭时隐藏模板准备内容，仅做直拳技术评估。
        ttk.Checkbutton(
            step1, text="启用模板比对（与标准动作模板计算相似度）",
            variable=self.do_compare_var, command=self._toggle_compare_section,
        ).pack(anchor="w")

        # 模板准备内容容器（受 do_compare_var 控制显隐）。
        self._template_body = ttk.Frame(step1)
        self._template_body.pack(fill="x", pady=(8, 0))

        # Mode selection
        mode_row = ttk.Frame(self._template_body)
        mode_row.pack(fill="x")
        ttk.Radiobutton(
            mode_row, text="使用已有模板", variable=self.template_mode_var, value="existing",
            command=self._toggle_template_mode
        ).pack(side="left")
        ttk.Radiobutton(
            mode_row, text="从视频生成", variable=self.template_mode_var, value="generate",
            command=self._toggle_template_mode
        ).pack(side="left", padx=(16, 0))

        # Existing template frame
        self._existing_frame = ttk.Frame(self._template_body)
        self._existing_frame.pack(fill="x", pady=(8, 0))
        ttk.Label(self._existing_frame, text="模板文件(.npz)：").grid(row=0, column=0, sticky="w")
        ttk.Entry(self._existing_frame, textvariable=self.template_var).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(self._existing_frame, text="选择…", command=self._browse_template).grid(row=0, column=2, padx=(8, 0))
        self._existing_frame.columnconfigure(1, weight=1)

        # Generate from video frame
        self._generate_frame = ttk.Frame(self._template_body)
        gen_row1 = ttk.Frame(self._generate_frame)
        gen_row1.pack(fill="x")
        ttk.Label(gen_row1, text="基准视频：").grid(row=0, column=0, sticky="w")
        ttk.Entry(gen_row1, textvariable=self.base_video_var).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(gen_row1, text="选择…", command=self._browse_base).grid(row=0, column=2, padx=(8, 0))
        gen_row1.columnconfigure(1, weight=1)

        # Advanced options (collapsible)
        self._advanced_section = CollapsibleSection(self._generate_frame, "高级选项", expanded=False)
        self._advanced_section.set_title("高级选项")
        self._advanced_section.pack_header(fill="x", pady=(8, 0))

        adv = self._advanced_section.content
        adv_row1 = ttk.Frame(adv)
        adv_row1.pack(fill="x", pady=(4, 0))
        ttk.Label(adv_row1, text="Pose 模型：").pack(side="left")
        ttk.Combobox(adv_row1, textvariable=self.pose_var, values=["lite", "full", "heavy"],
                     state="readonly", width=8).pack(side="left", padx=(6, 14))
        ttk.Label(adv_row1, text="线程数：").pack(side="left")
        ttk.Spinbox(adv_row1, from_=1, to=16, textvariable=self.workers_var, width=6).pack(side="left", padx=(6, 0))

        adv_row2 = ttk.Frame(adv)
        adv_row2.pack(fill="x", pady=(6, 0))
        ttk.Label(adv_row2, text="起始帧：").pack(side="left")
        ttk.Entry(adv_row2, textvariable=self.start_var, width=8).pack(side="left", padx=(6, 14))
        ttk.Label(adv_row2, text="结束帧：").pack(side="left")
        ttk.Entry(adv_row2, textvariable=self.end_var, width=8).pack(side="left", padx=(6, 0))

        self._gen_btn = ttk.Button(self._generate_frame, text="生成模板", command=self._gen_template)
        self._gen_btn.pack(fill="x", pady=(10, 0))

        # ===== Step 2: Target Video =====
        step2 = ttk.Labelframe(outer, text="② 选择目标视频", padding=10)
        step2.pack(fill="x", pady=(12, 0))

        tgt_row = ttk.Frame(step2)
        tgt_row.pack(fill="x")
        ttk.Label(tgt_row, text="目标视频：").grid(row=0, column=0, sticky="w")
        ttk.Entry(tgt_row, textvariable=self.target_video_var).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(tgt_row, text="选择…", command=self._browse_target).grid(row=0, column=2, padx=(8, 0))
        tgt_row.columnconfigure(1, weight=1)

        # 模板比对的「导出匹配片段预览」行（受 do_compare_var 控制显隐）。
        self._preview_row = ttk.Frame(step2)
        self._preview_row.pack(fill="x", pady=(8, 0))
        ttk.Checkbutton(
            self._preview_row, text="导出匹配片段预览", variable=self.save_preview_var, command=self._toggle_preview
        ).pack(side="left")
        self._preview_entry = ttk.Entry(self._preview_row, textvariable=self.preview_out_var, width=30)
        self._preview_entry.pack(side="left", padx=(8, 0), fill="x", expand=True)
        self._preview_btn = ttk.Button(self._preview_row, text="保存位置…", command=self._choose_preview_out)
        self._preview_btn.pack(side="left", padx=(8, 0))

        # ===== Step 2b: 直拳技术评估选项（融合自原「直拳检测」窗口，针对单视频）=====
        tech = ttk.Labelframe(outer, text="② 直拳技术评估", padding=10)
        tech.pack(fill="x", pady=(12, 0))
        ttk.Checkbutton(
            tech, text="启用直拳技术评估（重心 / 回收速度 / 发力顺序 / 拳面角度）",
            variable=self.do_tech_var, command=self._toggle_tech_section,
        ).pack(anchor="w")

        self._tech_body = ttk.Frame(tech)
        self._tech_body.pack(fill="x", pady=(8, 0))
        tech_opt = ttk.Frame(self._tech_body)
        tech_opt.pack(fill="x")
        ttk.Label(tech_opt, text="站姿：").pack(side="left")
        ttk.Combobox(tech_opt, textvariable=self.stance_var, values=["left", "right"], state="readonly", width=8).pack(
            side="left", padx=(6, 14)
        )
        ttk.Label(tech_opt, text="视角：").pack(side="left")
        ttk.Combobox(tech_opt, textvariable=self.view_var, values=["auto", "front", "side"], state="readonly", width=8).pack(
            side="left", padx=(6, 0)
        )
        ttk.Checkbutton(self._tech_body, text="导出调试视频（叠加骨架与指标）", variable=self.debug_video_var).pack(
            anchor="w", pady=(8, 0)
        )

        # ===== Step 3: Execute =====
        step3 = ttk.Labelframe(outer, text="③ 执行分析", padding=10)
        step3.pack(fill="x", pady=(12, 0))

        btn_row = ttk.Frame(step3)
        btn_row.pack(fill="x")
        self.start_btn = ttk.Button(btn_row, text="═══ 开始分析 ═══", command=self._start_compare)
        self.start_btn.pack(side="left", fill="x", expand=True)
        self.stop_btn = ttk.Button(btn_row, text="停止", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))

        # Progress bar (hidden initially)
        self._progress_frame = ttk.Frame(step3)
        self._progress_frame.pack(fill="x", pady=(8, 0))
        self.progress_bar = ttk.Progressbar(self._progress_frame, orient="horizontal", mode="determinate", maximum=100.0)
        self.progress_bar.pack(fill="x")
        ttk.Label(self._progress_frame, textvariable=self.progress_text_var).pack(anchor="w", pady=(4, 0))
        self._progress_frame.pack_forget()  # Hide initially

        # ===== Results =====
        result_frame = ttk.Labelframe(outer, text="结果", padding=10)
        result_frame.pack(fill="both", expand=True, pady=(12, 0))

        # Status line
        ttk.Label(result_frame, textvariable=self.status_var).pack(anchor="w")

        # Large score display
        self._score_frame = ttk.Frame(result_frame)
        self._score_frame.pack(fill="x", pady=(8, 0))

        self._score_label = ttk.Label(
            self._score_frame, text="—", font=("Helvetica", 36, "bold"), anchor="center"
        )
        self._score_label.pack()
        self._score_hint = ttk.Label(self._score_frame, text="相似度", anchor="center")
        self._score_hint.pack()

        # Match info
        self._match_label = ttk.Label(result_frame, textvariable=self.result_var, wraplength=600)
        self._match_label.pack(anchor="w", pady=(8, 0))

        # 直拳技术指标明细（受 do_tech_var 控制显隐）。
        self._detail_frame = ttk.Labelframe(result_frame, text="直拳技术指标", padding=8)
        self._detail_frame.pack(fill="both", expand=False, pady=(8, 0))
        detail_box = ttk.Frame(self._detail_frame)
        detail_box.pack(fill="both", expand=True)
        self.detail_text = Text(detail_box, height=9, wrap="none")
        self.detail_text.pack(side="left", fill="both", expand=True)
        detail_sb = Scrollbar(detail_box, command=self.detail_text.yview)
        detail_sb.pack(side="right", fill="y")
        self.detail_text.configure(yscrollcommand=detail_sb.set, state="disabled")

        # Collapsible JSON section
        self._json_section = CollapsibleSection(result_frame, "查看详细数据", expanded=False)
        self._json_section.set_title("查看详细数据")
        self._json_section.pack_header(fill="x", pady=(10, 0))

        json_content = self._json_section.content
        raw_box = ttk.Frame(json_content)
        raw_box.pack(fill="both", expand=True, pady=(4, 0))
        self.raw_text = Text(raw_box, height=10, wrap="none")
        self.raw_text.pack(side="left", fill="both", expand=True)
        sb = Scrollbar(raw_box, command=self.raw_text.yview)
        sb.pack(side="right", fill="y")
        self.raw_text.configure(yscrollcommand=sb.set)
        ttk.Button(json_content, text="复制数据", command=self._copy_raw).pack(anchor="e", pady=(6, 0))

        # Initialize display state
        self._toggle_template_mode()
        self._toggle_preview()
        self._toggle_compare_section()
        self._toggle_tech_section()
        self._reset_score_display()

    def _toggle_compare_section(self) -> None:
        """启用/停用模板比对：联动模板准备区、预览行与大号相似度显示的显隐。"""
        enabled = bool(self.do_compare_var.get())
        if enabled:
            self._template_body.pack(fill="x", pady=(8, 0))
            self._preview_row.pack(fill="x", pady=(8, 0))
            self._score_frame.pack(fill="x", pady=(8, 0))
        else:
            self._template_body.pack_forget()
            self._preview_row.pack_forget()
            self._score_frame.pack_forget()

    def _toggle_tech_section(self) -> None:
        """启用/停用直拳技术评估：联动选项区与指标明细框的显隐。"""
        enabled = bool(self.do_tech_var.get())
        if enabled:
            self._tech_body.pack(fill="x", pady=(8, 0))
            self._detail_frame.pack(fill="both", expand=False, pady=(8, 0))
        else:
            self._tech_body.pack_forget()
            self._detail_frame.pack_forget()

    def _toggle_preview(self) -> None:
        enabled = bool(self.save_preview_var.get())
        self._preview_entry.configure(state="normal" if enabled else "disabled")
        self._preview_btn.configure(state="normal" if enabled else "disabled")
        if not enabled:
            self.preview_out_var.set("")

    def _toggle_template_mode(self) -> None:
        """Switch between existing template and generate-from-video modes."""
        mode = self.template_mode_var.get()
        if mode == "existing":
            self._generate_frame.pack_forget()
            self._existing_frame.pack(fill="x", pady=(8, 0))
        else:
            self._existing_frame.pack_forget()
            self._generate_frame.pack(fill="x", pady=(8, 0))

    def _reset_score_display(self) -> None:
        """Reset score display to initial state."""
        self._last_score = None
        self._last_match_info = ""
        self._score_label.configure(text="—", foreground="")
        self.result_var.set("")

    def _update_score_display(self, score: float, match_info: str = "") -> None:
        """Update the large score display with color coding."""
        self._last_score = score
        self._last_match_info = match_info

        # Display as percentage
        pct = int(score * 100)
        self._score_label.configure(text=f"{pct}%")

        # Color coding based on score
        if score >= 0.8:
            color = "#2e7d32"  # Green - very similar
        elif score >= 0.5:
            color = "#f9a825"  # Yellow/amber - partial
        else:
            color = "#c62828"  # Red - different

        self._score_label.configure(foreground=color)
        self.result_var.set(match_info)

    def _show_progress(self, show: bool = True) -> None:
        """Show or hide the progress frame."""
        if show:
            self._progress_frame.pack(fill="x", pady=(8, 0))
        else:
            self._progress_frame.pack_forget()

    def _browse_base(self) -> None:
        p = filedialog.askopenfilename(
            title="选择基准视频",
            filetypes=[("视频文件", "*.mp4;*.avi;*.mov;*.mkv"), ("所有文件", "*.*")],
            parent=self._win,
        )
        self._win.lift()
        self._win.focus_force()
        if p:
            self.base_video_var.set(p)

    def _browse_target(self) -> None:
        p = filedialog.askopenfilename(
            title="选择目标视频",
            filetypes=[("视频文件", "*.mp4;*.avi;*.mov;*.mkv"), ("所有文件", "*.*")],
            parent=self._win,
        )
        self._win.lift()
        self._win.focus_force()
        if p:
            self.target_video_var.set(p)

    def _browse_template(self) -> None:
        p = filedialog.askopenfilename(
            title="选择模板文件",
            filetypes=[("模板文件", "*.npz"), ("所有文件", "*.*")],
            parent=self._win,
        )
        self._win.lift()
        self._win.focus_force()
        if p:
            self.template_var.set(p)

    def _choose_preview_out(self) -> None:
        p = filedialog.asksaveasfilename(
            title="保存匹配预览视频",
            defaultextension=".mp4",
            filetypes=[("MP4 视频", "*.mp4"), ("AVI 视频", "*.avi"), ("所有文件", "*.*")],
            parent=self._win,
        )
        self._win.lift()
        self._win.focus_force()
        if p:
            self.preview_out_var.set(p)

    def _parse_int_or_none(self, s: str) -> int | None:
        s = (s or "").strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            raise ValueError(f"请输入整数帧号：{s!r}")

    def _progress(self, stage: str, done: int, total: int) -> None:
        def _set() -> None:
            self._show_progress(True)
            if total > 0:
                self.progress_bar.configure(mode="determinate", maximum=float(total))
                self.progress_bar["value"] = float(done)
                pct = (done / total) * 100.0
                self.progress_text_var.set(f"{stage}：{done}/{total}（{pct:.1f}%）")
            else:
                self.progress_bar.configure(mode="determinate", maximum=100.0)
                self.progress_bar["value"] = 0.0
                self.progress_text_var.set(f"{stage}…")

        self._win.after(0, _set)

    def _set_status(self, text: str) -> None:
        self._win.after(0, lambda: self.status_var.set(text))

    def _set_result(self, text: str) -> None:
        self._win.after(0, lambda: self.result_var.set(text))

    def _set_raw(self, text: str) -> None:
        def _set() -> None:
            self.raw_text.delete("1.0", "end")
            self.raw_text.insert("1.0", text)

        self._win.after(0, _set)

    def _copy_raw(self) -> None:
        try:
            s = self.raw_text.get("1.0", "end").strip()
            self._win.clipboard_clear()
            self._win.clipboard_append(s)
            self._set_status("已复制原始数据到剪贴板")
        except Exception as e:
            messagebox.showerror("复制失败", str(e), parent=self._win)

    def _set_buttons(self, running: bool) -> None:
        def _set() -> None:
            self.start_btn.configure(state="disabled" if running else "normal")
            self.stop_btn.configure(state="normal" if running else "disabled")
            if not running:
                self._show_progress(False)

        self._win.after(0, _set)

    def _gen_template(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        base = self.base_video_var.get().strip()
        if not base:
            messagebox.showerror("配置错误", "请先选择基准视频。", parent=self._win)
            return

        try:
            start = self._parse_int_or_none(self.start_var.get())
            end = self._parse_int_or_none(self.end_var.get())
        except Exception as e:
            messagebox.showerror("配置错误", str(e), parent=self._win)
            return

        self._stop_evt.clear()
        self._set_buttons(True)
        self._set_status("正在生成模板…")
        self._reset_score_display()
        self._set_raw("")
        self._progress("准备中", 0, 0)

        def _run() -> None:
            try:
                tpl_path = create_template_from_video(
                    base,
                    pose_variant=self.pose_var.get(),
                    start=start,
                    end=end,
                    workers=int(self.workers_var.get() or 1),
                    preview=False,
                    progress_cb=self._progress,
                    stop_evt=self._stop_evt,
                )
                self._win.after(0, lambda: self.template_var.set(str(tpl_path)))
                self._set_status("模板生成完成")
                self._set_result(f"模板：{tpl_path}")
                payload = {"template_path": str(tpl_path)}
                self._set_raw(json.dumps(payload, ensure_ascii=False, indent=2))
            except Exception as e:
                self._set_status("模板生成失败")
                self._set_result(str(e))
                self._set_raw("")
            finally:
                self._set_buttons(False)

        self._worker = threading.Thread(target=_run, daemon=True)
        self._worker.start()

    def _set_detail(self, text: str) -> None:
        if self.detail_text is None:
            return

        def _set() -> None:
            if self.detail_text is None:
                return
            self.detail_text.configure(state="normal")
            self.detail_text.delete("1.0", "end")
            self.detail_text.insert("1.0", text)
            self.detail_text.configure(state="disabled")

        self._win.after(0, _set)

    def _start_compare(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        do_compare = bool(self.do_compare_var.get())
        do_tech = bool(self.do_tech_var.get())
        if not do_compare and not do_tech:
            messagebox.showerror("配置错误", "请至少启用「模板比对」或「直拳技术评估」之一。", parent=self._win)
            return

        tpl = self.template_var.get().strip()
        vid = self.target_video_var.get().strip()
        if not vid:
            messagebox.showerror("配置错误", "请先选择目标视频。", parent=self._win)
            return
        if do_compare and not tpl:
            messagebox.showerror("配置错误", "已启用模板比对，请先选择模板文件（.npz），或从基准视频生成模板。", parent=self._win)
            return

        preview_out = None
        if do_compare and self.save_preview_var.get():
            preview_out = self.preview_out_var.get().strip()
            if not preview_out:
                preview_out = str(Path(tpl).with_suffix(".match.preview.avi"))
                self.preview_out_var.set(preview_out)

        pose_variant = self.pose_var.get().strip() or "full"
        stance = self.stance_var.get().strip() or "left"
        view_hint = self.view_var.get().strip() or "auto"
        want_debug = do_tech and bool(self.debug_video_var.get())
        workers = int(self.workers_var.get() or 1)

        self._stop_evt.clear()
        self._set_buttons(True)
        self._set_status("正在分析…")
        self._reset_score_display()
        self._set_detail("")
        self._set_raw("")
        self._progress("准备中", 0, 0)

        def _run() -> None:
            payload: dict = {"video_path": vid}
            match_info_parts: list[str] = []
            try:
                # ① 模板比对（可选）
                if do_compare:
                    res = compare_video_to_template(
                        tpl,
                        vid,
                        pose_variant=pose_variant,
                        workers=workers,
                        preview_out=preview_out,
                        progress_cb=self._progress,
                        stop_evt=self._stop_evt,
                    )
                    tpl_meta = {}
                    try:
                        d = np.load(tpl, allow_pickle=True)
                        tpl_meta = d["meta"].item()
                    except Exception:
                        tpl_meta = {}
                    payload["compare"] = {
                        "score": res.score,
                        "avg_cost": res.avg_cost,
                        "cost": res.cost,
                        "start_frame": res.start_frame,
                        "end_frame": res.end_frame,
                        "fps": res.fps,
                        "pose_variant": res.pose_variant,
                        "workers_used": res.workers_used,
                        "template_path": str(res.template_path),
                        "preview_path": str(res.preview_path) if res.preview_path else None,
                        "template_meta": tpl_meta,
                    }
                    match_info_parts.append(
                        f"匹配片段：帧 {res.start_frame}..{res.end_frame}  "
                        f"时间 {res.start_frame/res.fps:.2f}s ~ {res.end_frame/res.fps:.2f}s"
                    )
                    if res.workers_used and res.workers_used != workers:
                        match_info_parts.append("说明：模板为 VIDEO 模式，已自动使用单线程以保证准确。")
                    if res.preview_path:
                        self._win.after(0, lambda p=res.preview_path: self.preview_out_var.set(str(p)))
                        match_info_parts.append(f"预览导出：{res.preview_path}")
                    score = res.score
                    self._win.after(0, lambda: self._update_score_display(score, "\n".join(match_info_parts)))

                if self._stop_evt.is_set():
                    self._set_status("已停止")
                    return

                # ② 直拳技术评估（可选）
                if do_tech:
                    self._progress("技术评估中", 0, 0)
                    self._run_tech_eval(
                        Path(vid), pose_variant=pose_variant, stance=stance,
                        view_hint=view_hint, want_debug=want_debug, payload=payload,
                    )

                self._set_raw(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2))
                if not do_compare:
                    self._set_result("\n".join(match_info_parts) if match_info_parts else "技术评估完成")
                self._set_status("分析完成")
            except Exception as e:
                self._set_status("分析失败")
                self._set_result(str(e))
                self._set_raw("")
            finally:
                self._set_buttons(False)

        self._worker = threading.Thread(target=_run, daemon=True)
        self._worker.start()

    def _run_tech_eval(
        self, video: Path, *, pose_variant: str, stance: str, view_hint: str,
        want_debug: bool, payload: dict,
    ) -> None:
        """对单个视频执行直拳技术评估，写入指标明细文本与 payload。"""
        def _cause(ind: object) -> str:
            detail = getattr(ind, "detail", None)
            return str(detail.get("primary_cause") or "") if isinstance(detail, dict) else ""

        def _failed_stage(ind: object) -> str | None:
            detail = getattr(ind, "detail", None)
            if not isinstance(detail, dict):
                return None
            val = detail.get("failed_stage")
            return None if val in (None, "") else str(val)

        def _fmt(label: str, ind: object | None) -> str:
            if ind is None:
                return f"{label}: 未评估"
            parts = [f"{label}: {getattr(ind, 'status', '')}", str(getattr(ind, "reason", ""))]
            if _cause(ind):
                parts.append(f"原因类型: {_cause(ind)}")
            if _failed_stage(ind):
                parts.append(f"失败环节: {_failed_stage(ind)}")
            return " | ".join(p for p in parts if p)

        if want_debug:
            res, lm, vs, meta = evaluate_video_assets(
                video, pose_variant=pose_variant, stance=stance, view_hint=view_hint
            )
        else:
            res = evaluate_video_detail(
                video, pose_variant=pose_variant, stance=stance, view_hint=view_hint
            )
            lm = vs = meta = None

        detail_lines = [
            f"视频: {video.name}",
            f"视角模式: {res.view_mode}",
            _fmt("重心(侧面优先)", res.cog_final),
            _fmt("重心_侧面", res.cog_side),
            _fmt("重心_正面", res.cog_front),
            _fmt("重心_CoM(方案3)", res.cog_com),
            _fmt("回收速度", res.retract_speed),
            _fmt("发力顺序", res.force_sequence),
            _fmt("拳面角度", res.wrist_angle),
        ]
        self._set_detail("\n".join(detail_lines))

        payload["tech_eval"] = {
            "pose_variant": pose_variant,
            "fps": float(res.fps),
            "view_mode": str(res.view_mode),
            "cog_side": res.cog_side,
            "cog_front": res.cog_front,
            "cog_final": res.cog_final,
            "cog_com": res.cog_com,
            "retract_speed": res.retract_speed,
            "force_sequence": res.force_sequence,
            "wrist_angle": res.wrist_angle,
        }

        if want_debug and lm is not None and vs is not None and meta is not None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_mp4 = outputs_dir() / f"{video.stem}_debug_{ts}.mp4"
            export_debug_video(
                video, out_mp4, pose_variant=pose_variant, stance=stance,
                view_hint=view_hint, res=res, landmarks=lm, view_scores=vs, meta=meta,
            )
            payload["tech_eval"]["debug_video"] = str(out_mp4)

    def _stop(self) -> None:
        self._stop_evt.set()
        self._set_status("正在停止…")

    def _on_close(self) -> None:
        self._stop_evt.set()
        self._win.destroy()


@dataclass(frozen=True)
class UiState:
    source: str
    pose_variant: str
    workers: int
    enable_hands: bool
    out_path: str | None = None
    source2: str | None = None


class SettingsWindow:
    """设置窗口：模型管理（查看当前模型 / 下载缺失模型）。

    本期仅提供 MediaPipe 模型下载。下载源为 Google 官方直链；若用户网络无法访问，
    会在状态区提示自行解决网络问题（代理 / 加速等）。
    """

    def __init__(self, parent: Tk, *, current_pose: str = "full", hands_enabled: bool = True) -> None:
        self._win = Toplevel(parent)
        self._win.title("设置")
        self._win.geometry("560x560")
        self._win.minsize(520, 500)

        # 主界面当前选择：用于在模型列表中标注「当前使用」并在顶部汇总展示。
        self._current_pose = (current_pose or "full").strip().lower()
        self._hands_enabled = bool(hands_enabled)
        # 当前实际会用到的模型 key 集合（pose 选档 + 可选 hand）。
        self._active_keys = {
            {"lite": "pose_lite", "full": "pose_full", "heavy": "pose_heavy"}.get(
                self._current_pose, "pose_full"
            )
        }
        if self._hands_enabled:
            self._active_keys.add("hand")

        self.status_var = StringVar(value="就绪")
        self.progress_text_var = StringVar(value="")
        self.current_model_var = StringVar(value="")

        # 每个模型一行的控件引用：key -> dict(state_var, btn)
        self._rows: dict[str, dict] = {}

        self._stop_evt = threading.Event()
        self._worker: threading.Thread | None = None

        self._build()
        self._refresh_states()
        self._win.protocol("WM_DELETE_WINDOW", self._on_close)

    def is_open(self) -> bool:
        return bool(self._win.winfo_exists())

    def focus(self) -> None:
        try:
            self._win.deiconify()
            self._win.lift()
            self._win.focus_force()
        except Exception:
            pass

    def _build(self) -> None:
        outer = ttk.Frame(self._win, padding=12)
        outer.pack(fill="both", expand=True)

        # ===== 当前模型 =====
        current_frame = ttk.Labelframe(outer, text="当前模型", padding=10)
        current_frame.pack(fill="x")
        ttk.Label(
            current_frame,
            textvariable=self.current_model_var,
            wraplength=510,
        ).pack(anchor="w")

        # ===== 模型管理 =====
        mp_frame = ttk.Labelframe(outer, text="MediaPipe 模型", padding=10)
        mp_frame.pack(fill="x", pady=(12, 0))

        ttk.Label(
            mp_frame,
            text="模型目录：" + str(models_dir()),
            wraplength=500,
        ).pack(anchor="w", pady=(0, 8))

        for spec in model_manager.MEDIAPIPE_MODELS:
            row = ttk.Frame(mp_frame)
            row.pack(fill="x", pady=(4, 0))

            name = ttk.Label(row, text=spec.label, width=34, anchor="w")
            name.grid(row=0, column=0, sticky="w")

            state_var = StringVar(value="检查中…")
            state_lbl = ttk.Label(row, textvariable=state_var, width=14, anchor="w")
            state_lbl.grid(row=0, column=1, sticky="w", padx=(8, 0))

            btn = ttk.Button(
                row, text="下载", width=8,
                command=lambda s=spec: self._download(s),
            )
            btn.grid(row=0, column=2, sticky="e", padx=(8, 0))
            row.columnconfigure(0, weight=1)

            self._rows[spec.key] = {"spec": spec, "state_var": state_var, "btn": btn}

        # 一键下载缺失模型
        bulk_row = ttk.Frame(mp_frame)
        bulk_row.pack(fill="x", pady=(12, 0))
        self.download_all_btn = ttk.Button(
            bulk_row, text="下载全部缺失模型", command=self._download_missing
        )
        self.download_all_btn.pack(side="left")
        self.refresh_btn = ttk.Button(bulk_row, text="刷新状态", command=self._refresh_states)
        self.refresh_btn.pack(side="left", padx=(8, 0))

        # ===== 进度 / 状态 =====
        status_frame = ttk.Labelframe(outer, text="状态", padding=10)
        status_frame.pack(fill="both", expand=True, pady=(12, 0))

        ttk.Label(status_frame, textvariable=self.status_var, wraplength=510).pack(anchor="w")
        self.progress_bar = ttk.Progressbar(
            status_frame, orient="horizontal", mode="determinate", maximum=100.0
        )
        self.progress_bar.pack(fill="x", pady=(8, 0))
        ttk.Label(status_frame, textvariable=self.progress_text_var, wraplength=510).pack(
            anchor="w", pady=(4, 0)
        )
        ttk.Label(
            status_frame,
            text="说明：模型从 Google 官方源下载。若长时间无进度或失败，通常是网络无法访问"
            " storage.googleapis.com，请自行配置代理后重试。",
            wraplength=510,
            foreground="#666",
        ).pack(anchor="w", pady=(10, 0))

    def _busy(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _refresh_states(self) -> None:
        """刷新每个模型的「已安装 / 未安装」状态显示，并标注当前使用的模型。"""
        for key, info in self._rows.items():
            spec = info["spec"]
            active = key in self._active_keys
            mark = "● 使用中  " if active else ""
            if model_manager.is_installed(spec):
                size = model_manager.installed_size_mb(spec)
                info["state_var"].set(mark + (f"已安装 ({size} MB)" if size else "已安装"))
                info["btn"].configure(text="重新下载")
            else:
                approx = f"约 {spec.approx_mb} MB" if spec.approx_mb else ""
                info["state_var"].set((mark + f"未安装 {approx}").strip())
                info["btn"].configure(text="下载")

        self._refresh_current_summary()

    def _refresh_current_summary(self) -> None:
        """汇总当前主界面所选模型及其就绪情况，写入「当前模型」区。"""
        parts: list[str] = []
        missing: list[str] = []
        for key in ("pose_lite", "pose_full", "pose_heavy", "hand"):
            if key not in self._active_keys:
                continue
            info = self._rows.get(key)
            if info is None:
                continue
            spec = info["spec"]
            ready = model_manager.is_installed(spec)
            parts.append(f"{spec.label}（{'已就绪' if ready else '缺失'}）")
            if not ready:
                missing.append(spec.label)
        hands_txt = "开启" if self._hands_enabled else "关闭"
        summary = f"姿态模型：{self._current_pose}　手部检测：{hands_txt}\n" + "\n".join(parts)
        if missing:
            summary += "\n\n⚠ 缺失模型会导致无法开始识别，请在下方下载后再使用。"
        self.current_model_var.set(summary)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for info in self._rows.values():
            info["btn"].configure(state=state)
        self.download_all_btn.configure(state=state)
        self.refresh_btn.configure(state=state)

    def _set_status(self, text: str) -> None:
        self._win.after(0, lambda: self.status_var.set(text))

    def _set_progress(self, downloaded: int, total: int | None) -> None:
        def _set() -> None:
            if total and total > 0:
                pct = (downloaded / total) * 100.0
                self.progress_bar.configure(mode="determinate", maximum=100.0)
                self.progress_bar["value"] = pct
                self.progress_text_var.set(
                    f"{downloaded / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MB（{pct:.0f}%）"
                )
            else:
                self.progress_bar.configure(mode="determinate", maximum=100.0)
                self.progress_bar["value"] = 0.0
                self.progress_text_var.set(f"{downloaded / 1024 / 1024:.1f} MB…")

        self._win.after(0, _set)

    def _download(self, spec: "model_manager.ModelSpec") -> None:
        self._start_download([spec])

    def _download_missing(self) -> None:
        missing = [info["spec"] for info in self._rows.values()
                   if not model_manager.is_installed(info["spec"])]
        if not missing:
            messagebox.showinfo("模型管理", "所有模型均已安装。", parent=self._win)
            return
        self._start_download(missing)

    def _start_download(self, specs: list) -> None:
        if self._busy():
            return
        self._stop_evt.clear()
        self._set_buttons_enabled(False)

        def _run() -> None:
            ok, failed = 0, []
            try:
                for spec in specs:
                    if self._stop_evt.is_set():
                        break
                    self._set_status(f"正在下载：{spec.label} …")
                    try:
                        model_manager.download_model(
                            spec,
                            progress_cb=self._set_progress,
                            should_stop=self._stop_evt.is_set,
                        )
                        ok += 1
                        self._win.after(0, self._refresh_states)
                    except InterruptedError:
                        self._set_status("下载已取消。")
                        return
                    except Exception as e:  # noqa: BLE001
                        failed.append((spec.label, str(e)))
                if failed:
                    detail = "\n".join(f"- {name}: {err}" for name, err in failed)
                    self._set_status(f"完成 {ok} 个，{len(failed)} 个失败。")
                    self._win.after(
                        0,
                        lambda: messagebox.showerror(
                            "下载失败",
                            "以下模型下载失败（多为网络无法访问 Google 源，请配置代理后重试）：\n\n"
                            + detail,
                            parent=self._win,
                        ),
                    )
                else:
                    self._set_status(f"全部完成，共下载 {ok} 个模型。")
            finally:
                self._win.after(0, self._refresh_states)
                self._win.after(0, lambda: self._set_buttons_enabled(True))

        self._worker = threading.Thread(target=_run, daemon=True)
        self._worker.start()

    def _on_close(self) -> None:
        self._stop_evt.set()
        self._win.destroy()


class App:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("MediaPipe 动作识别（人体姿态 + 手部）")
        self.root.geometry("1100x720")
        # 控制区改为可滚动容器后，限制窗口最小尺寸，保证滚动条与预览区可用（需求 1.5/1.6）。
        self.root.minsize(800, 600)

        self.source_var = StringVar(value="")
        self.camera_choice_var = StringVar(value="")
        self.camera_choice_var_2 = StringVar(value=NO_SECOND_CAMERA)
        self.source_hint_var = StringVar(value="当前输入源：未选择")
        self.pose_var = StringVar(value="full")
        self.workers_var = IntVar(value=2)
        self.enable_hands_var = BooleanVar(value=True)
        # 录制视频保存目录（默认 outputs_dir()）。录制文件名仍由控制器按时间戳生成。
        self.record_dir_var = StringVar(value=str(outputs_dir()))
        self.status_var = StringVar(value="就绪")
        self.actions_var = StringVar(value="-")
        self.progress_var = DoubleVar(value=0.0)
        self.progress_text_var = StringVar(value="")
        # 录制状态文本与 Result_Video 完整路径（需求 5.9/5.10）。对应的 Label 控件
        # 由任务 9.3 在 _build_ui 中加入，此处先维护变量。
        self.recording_status_var = StringVar(value="")
        # 守卫标志：避免每 30ms 重复弹出同一录制错误对话框（需求 5.11）。
        self._record_error_shown = False

        # 输入源状态模型（camera / video / none 三态互斥）。
        self._source_state = InputSourceState()
        self._camera_entries: list[CameraEntry] = []
        self._enum_busy = threading.Event()

        self._stop_evt = threading.Event()
        self._worker: threading.Thread | None = None
        self._queue: Queue[tuple[np.ndarray, str]] = Queue(maxsize=1)
        self._photo: ImageTk.PhotoImage | None = None
        self._compare_win: CompareWindow | None = None
        self._settings_win: SettingsWindow | None = None
        self._settings_win: SettingsWindow | None = None

        # 录制/暂停运行时控制器（与 Tkinter 解耦的状态机）。使用模块默认的
        # writer_factory（绑定 core.video_writer.open_video_writer）。path_provider
        # 注入为读取 self.record_dir_var 的闭包：用户在「录制」分组选择的保存目录
        # 下，按时间戳生成 record_<timestamp>.mp4。录制流程完全由该控制器管理。
        self._rec = RecordingController(path_provider=self._record_path)

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._tick()
        # 启动时后台枚举可用摄像头（需求 1.1）。
        self._start_enumeration()

    def _build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=0)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        # Left: scrollable controls container（可滚动 Canvas + 垂直 Scrollbar + 内嵌 inner Frame，需求 1.5/1.6）。
        # outer 列 0 固定宽度容器；列 1 预览区可伸展。
        left_container = ttk.Frame(outer)
        left_container.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        left_container.rowconfigure(0, weight=1)

        self.left_canvas = Canvas(left_container, width=360, highlightthickness=0, borderwidth=0)
        self.left_canvas.grid(row=0, column=0, sticky="ns")
        left_scroll = ttk.Scrollbar(left_container, orient="vertical", command=self.left_canvas.yview)
        left_scroll.grid(row=0, column=1, sticky="ns")
        self.left_canvas.configure(yscrollcommand=left_scroll.set)

        # 内嵌 inner Frame 作为所有控制卡片的父容器。
        self.controls_inner = ttk.Frame(self.left_canvas)
        self._controls_window = self.left_canvas.create_window(
            (0, 0), window=self.controls_inner, anchor="nw"
        )

        # inner 内容尺寸变化时更新 scrollregion；同时让 inner 宽度跟随 canvas 宽度。
        def _on_inner_configure(event: object) -> None:
            self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))

        self.controls_inner.bind("<Configure>", _on_inner_configure)

        def _on_canvas_configure(event: "Event") -> None:
            self.left_canvas.itemconfigure(self._controls_window, width=event.width)

        self.left_canvas.bind("<Configure>", _on_canvas_configure)

        # 鼠标滚轮滚动（Windows: <MouseWheel> + event.delta）。指针进入控制区时绑定，离开时解绑。
        def _on_mousewheel(event: "Event") -> None:
            self.left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mousewheel(event: object) -> None:
            self.left_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(event: object) -> None:
            self.left_canvas.unbind_all("<MouseWheel>")

        self.left_canvas.bind("<Enter>", _bind_mousewheel)
        self.left_canvas.bind("<Leave>", _unbind_mousewheel)
        self.controls_inner.bind("<Enter>", _bind_mousewheel)
        self.controls_inner.bind("<Leave>", _unbind_mousewheel)

        # 所有左侧控制卡片改为放入可滚动的 inner Frame。
        left = self.controls_inner

        # ===== Primary_Controls 分组（核心五项，固定顺序，需求 1.1/1.3）=====
        # 自上而下恰好五项：Camera_Selector → Model_Selector → Start_Control
        # → Record_Toggle → Compare_Control，相邻控件之间不插入任何 Secondary_Option。
        primary = ttk.Labelframe(left, text="主要操作", padding=10)
        primary.pack(fill="x", pady=(0, 10))

        # 0) 顶部工具行：右上角「设置」按钮（模型管理等）。
        top_row = ttk.Frame(primary)
        top_row.pack(fill="x")
        self.settings_btn = ttk.Button(top_row, text="⚙ 设置", width=8, command=self._open_settings)
        self.settings_btn.pack(side="right")

        # 1) Camera_Selector：摄像头下拉 + 刷新按钮（刷新为摄像头选择的附属操作，允许同行）。
        ttk.Label(primary, text="选择摄像头：").pack(anchor="w")
        cam_row = ttk.Frame(primary)
        cam_row.pack(fill="x", pady=(6, 0))
        self.camera_combo = ttk.Combobox(
            cam_row, textvariable=self.camera_choice_var, state="readonly"
        )
        self.camera_combo.pack(side="left", fill="x", expand=True)
        self.camera_combo.bind("<<ComboboxSelected>>", self._on_camera_selected)
        self.refresh_btn = ttk.Button(cam_row, text="刷新", command=self._refresh_cameras)
        self.refresh_btn.pack(side="left", padx=(8, 0))

        # 1b) 第二摄像头（可选，双摄双面视图预览，issue #57）：默认「无」，不影响单摄路径。
        ttk.Label(primary, text="第二摄像头（可选，双摄预览）：").pack(anchor="w", pady=(10, 0))
        self.camera_combo_2 = ttk.Combobox(
            primary,
            textvariable=self.camera_choice_var_2,
            values=[NO_SECOND_CAMERA],
            state="readonly",
        )
        self.camera_combo_2.pack(fill="x", pady=(6, 0))

        # 2) Model_Selector：人体姿态模型下拉（绑定 self.model_combo，供运行态联动引用）。
        ttk.Label(primary, text="人体姿态模型：").pack(anchor="w", pady=(10, 0))
        self.model_combo = ttk.Combobox(
            primary, textvariable=self.pose_var, values=["lite", "full", "heavy"], state="readonly"
        )
        self.model_combo.pack(fill="x", pady=(6, 0))

        # 3) Start_Control：开始/停止（保留分离的 start/stop 双按钮与既有 _start/_stop 接线）。
        start_row = ttk.Frame(primary)
        start_row.pack(fill="x", pady=(10, 0))
        self.start_btn = ttk.Button(start_row, text="开始", command=self._start)
        self.start_btn.pack(side="left", fill="x", expand=True)
        self.stop_btn = ttk.Button(start_row, text="停止", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", fill="x", expand=True, padx=(8, 0))

        # 4) Record_Controls：录制相关操作独立成组，与会话级 Start_Control（开始/停止）
        #    在视觉上区分开。组内含两个动作（需求 5.x）：
        #      - record_btn（三态切换）：开始录制 / 暂停录制 / 继续录制。
        #      - record_stop_btn（结束录制）：结束当前录制片段并落盘，但不结束识别会话，
        #        随后可在同一会话内再次「开始录制」生成新文件。
        #    会话未运行时整组禁用（需求 5.1）。
        record_group = ttk.Labelframe(primary, text="录制", padding=8)
        record_group.pack(fill="x", pady=(10, 0))
        self.record_btn = ttk.Button(
            record_group, text=RECORD_BTN_TEXT["idle"], command=self._on_record_toggle, state="disabled"
        )
        self.record_btn.pack(fill="x")
        self.record_stop_btn = ttk.Button(
            record_group, text="结束录制", command=self._on_record_stop, state="disabled"
        )
        self.record_stop_btn.pack(fill="x", pady=(6, 0))

        # 录制视频保存目录选择行：默认 outputs_dir()，可改到任意目录。
        ttk.Label(record_group, text="保存目录：").pack(anchor="w", pady=(8, 0))
        record_dir_row = ttk.Frame(record_group)
        record_dir_row.pack(fill="x", pady=(2, 0))
        self.record_dir_entry = ttk.Entry(record_dir_row, textvariable=self.record_dir_var)
        self.record_dir_entry.pack(side="left", fill="x", expand=True)
        self.record_dir_btn = ttk.Button(record_dir_row, text="选择…", command=self._choose_record_dir)
        self.record_dir_btn.pack(side="left", padx=(8, 0))

        # 5) Compare_Control：动作分析（模板比对 + 直拳技术评估，绑定 self.compare_btn）。
        self.compare_btn = ttk.Button(primary, text="动作分析…", command=self._open_compare)
        self.compare_btn.pack(fill="x", pady=(10, 0))

        # ===== 可见分隔线：在 Primary_Controls 与 Secondary_Options 之间插入显式
        # 水平分隔，强化主/次分区（需求 1.2）。布局测试可通过该属性定位。=====
        self.primary_secondary_separator = ttk.Separator(left, orient="horizontal")
        self.primary_secondary_separator.pack(fill="x", pady=8)

        # ===== Secondary_Options 分组（次要选项，统一置于 Compare_Control 之后，
        # 需求 1.4/7.1/7.2/7.3/7.4）。=====
        secondary = ttk.Labelframe(left, text="次要选项", padding=10)
        secondary.pack(fill="x", pady=(0, 10))

        # 输入源提示（显示当前选中的摄像头）。
        ttk.Label(secondary, textvariable=self.source_hint_var, wraplength=320).pack(
            anchor="w"
        )

        # 线程数（视频文件离线处理 / 摄像头实时并行；需求 7.2）。
        ttk.Label(secondary, text="线程数（>1：多核并行，关闭时序平滑）：").pack(anchor="w", pady=(10, 0))
        self.workers_spin = ttk.Spinbox(secondary, from_=1, to=16, textvariable=self.workers_var, width=6)
        self.workers_spin.pack(anchor="w", pady=(6, 0))

        # 启用手部检测（需求 7.3）。
        ttk.Checkbutton(secondary, text="启用手部检测（V 手势 / 手部骨架）", variable=self.enable_hands_var).pack(
            anchor="w", pady=(10, 0)
        )

        # ===== Status_Area（状态区，固定置于控制区底部，需求 7.6/7.7/7.8）。=====
        info = ttk.Labelframe(left, text="状态", padding=10)
        info.pack(fill="x")
        ttk.Label(info, textvariable=self.status_var, wraplength=320).pack(anchor="w")
        # 录制状态文本与 Result_Video 完整路径（需求 5.9/5.10）。
        ttk.Label(info, textvariable=self.recording_status_var, wraplength=320).pack(anchor="w", pady=(4, 0))
        ttk.Label(info, text="识别结果：").pack(anchor="w", pady=(8, 0))
        ttk.Label(info, textvariable=self.actions_var, wraplength=320).pack(anchor="w")
        ttk.Label(info, textvariable=self.progress_text_var, wraplength=320).pack(anchor="w", pady=(8, 0))
        self.progress_bar = ttk.Progressbar(info, orient="horizontal", mode="determinate", maximum=100.0)
        self.progress_bar.pack(fill="x", pady=(6, 0))
        ttk.Label(info, text="提示：点击“停止”结束识别。").pack(anchor="w", pady=(8, 0))

        # Right: preview
        right = ttk.Labelframe(outer, text="预览", padding=10)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self.preview = ttk.Label(right)
        self.preview.grid(row=0, column=0, sticky="nsew")

    def _open_compare(self) -> None:
        if self._compare_win and self._compare_win.is_open():
            self._compare_win.focus()
            return
        # 比对窗口创建失败时弹框并保持主窗口状态不变（需求 6.3）：
        # 不修改 self._compare_win（保留先前值/None），主窗口控件与录制状态均不受影响。
        try:
            win = CompareWindow(self.root)
        except Exception as e:
            messagebox.showerror("打开失败", f"动作比对窗口创建失败：{e}")
            return
        self._compare_win = win

    def _open_settings(self) -> None:
        if self._settings_win and self._settings_win.is_open():
            self._settings_win.focus()
            return
        try:
            win = SettingsWindow(
                self.root,
                current_pose=self.pose_var.get(),
                hands_enabled=bool(self.enable_hands_var.get()),
            )
        except Exception as e:
            messagebox.showerror("打开失败", f"设置窗口创建失败：{e}")
            return
        self._settings_win = win

    def _record_path(self) -> Path:
        """RecordingController 的 path_provider：在用户选择的录制目录下按时间戳生成文件名。

        目录取自 self.record_dir_var；为空时回退到 outputs_dir()。文件名沿用
        record_<timestamp>.mp4 约定，确保同一目录内多次录制不互相覆盖。
        """
        base = self.record_dir_var.get().strip()
        directory = Path(base) if base else outputs_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return directory / f"record_{timestamp}.mp4"

    def _choose_record_dir(self) -> None:
        """选择录制视频保存目录。"""
        current = self.record_dir_var.get().strip()
        d = filedialog.askdirectory(
            title="选择录制视频保存目录",
            initialdir=current or str(outputs_dir()),
        )
        if d:
            self.record_dir_var.set(d)

    def _on_record_toggle(self) -> None:
        """Record_Toggle 点击回调：请求录制状态机切换，并据返回状态刷新按钮文本。

        idle→开始录制、recording→暂停录制、paused→继续录制（见 RECORD_BTN_TEXT）。
        Record_Toggle 控件由任务 9.2 在 _build_ui 中创建并绑定到 self.record_btn；
        此处对其存在性做保护，使方法在控件尚未创建时仍可安全调用。
        """
        new_state = self._rec.request_toggle()
        record_btn = getattr(self, "record_btn", None)
        if record_btn is not None:
            record_btn.configure(text=RECORD_BTN_TEXT[new_state])
        # 「结束录制」仅在存在录制片段（recording/paused）时可用。
        sync_record_stop = getattr(self, "_sync_record_stop_enabled", None)
        if sync_record_stop is not None:
            sync_record_stop(new_state)

    def _on_record_stop(self) -> None:
        """「结束录制」点击回调：结束当前录制片段并落盘，但不结束识别会话。

        调用控制器 ``stop_recording()`` 复位为 idle（保持会话运行），随后把切换按钮
        文本复位为「开始录制」、禁用「结束录制」，使用户可在同一会话内重新开始录制。
        """
        self._rec.stop_recording()
        record_btn = getattr(self, "record_btn", None)
        if record_btn is not None:
            record_btn.configure(text=RECORD_BTN_TEXT["idle"])
        self._sync_record_stop_enabled("idle")

    def _sync_record_stop_enabled(self, state: RecordingState) -> None:
        """根据录制状态联动「结束录制」按钮的可用性：recording/paused 启用，idle 禁用。"""
        record_stop_btn = getattr(self, "record_stop_btn", None)
        if record_stop_btn is not None:
            try:
                record_stop_btn.configure(
                    state="normal" if state in ("recording", "paused") else "disabled"
                )
            except Exception:
                pass

    def _refresh_recording_status(self) -> None:
        """周期性（由 _tick 每 tick 调用）刷新录制状态文本与错误提示。

        - recording/paused：在 recording_status_var 显示状态文本与 Result_Video
          的完整保存路径（需求 5.9）。
        - idle：清除录制状态文本与路径（需求 5.10）。
        - last_error 非空：弹出包含失败原因的错误提示、复位录制按钮文本到
          「开始录制」、清除录制文本（需求 5.11）。用 _record_error_shown 守卫，
          避免每 30ms 重复弹框。
        """
        snap = self._rec.snapshot()

        if snap.last_error is not None:
            if not self._record_error_shown:
                self._record_error_shown = True
                record_btn = getattr(self, "record_btn", None)
                if record_btn is not None:
                    record_btn.configure(text=RECORD_BTN_TEXT["idle"])
                self._sync_record_stop_enabled("idle")
                self.recording_status_var.set("")
                messagebox.showerror("录制失败", f"录制发生错误：{snap.last_error}")
            return

        # 无错误：复位守卫，下次错误可再次提示。
        self._record_error_shown = False

        if snap.state in ("recording", "paused"):
            path_text = str(snap.result_path) if snap.result_path is not None else "（准备中）"
            label = "录制中" if snap.state == "recording" else "已暂停"
            self.recording_status_var.set(f"{label}：{path_text}")
        else:  # idle
            self.recording_status_var.set("")
        # 「结束录制」按钮可用性跟随真实状态联动（覆盖 worker 端错误复位等情形）。
        self._sync_record_stop_enabled(snap.state)

    def _set_running_controls(self, running: bool) -> None:
        """集中管理运行态控件的 enable/disable 与文本联动（需求 2.5、3.5、3.6、4.3、4.5、5.1、5.2、6.4、6.5）。

        运行中（running=True）：
          - 禁用 Camera_Selector（需求 2.5）与刷新控件（经 _set_refresh_enabled）。
          - 禁用 Model_Selector（需求 3.5）。
          - 启用 Record_Toggle 并置文本「开始录制」（需求 5.2）。
          - Start_Control 切换为「停止」语义：兼容现有分离的 start/stop 双按钮——禁用
            start_btn、启用 stop_btn，并将 start_btn 文本置为「停止」（需求 4.3）。
        未运行（running=False）：
          - 恢复 Camera_Selector 为 readonly（仅当存在可选摄像头列表时）与刷新控件。
          - 恢复 Model_Selector 为 readonly（需求 3.6）。
          - 禁用 Record_Toggle（需求 5.1）；录制状态由 worker 的 close_session 复位为 idle，
            此处不调用控制器方法以免误触发。
          - Start_Control 恢复为「开始」：启用 start_btn、禁用 stop_btn。
          - Status_Area 显示「就绪」（需求 4.5）。
        Compare_Control 始终保持 enabled（需求 6.4、6.5）。

        record_btn / model_combo / compare_btn 由任务 9.x 在 _build_ui 中创建，此处用
        getattr 守卫，保证在它们尚未创建时方法仍可安全调用。
        """
        # Camera_Selector：运行中禁用；未运行时仅当有可选摄像头列表才恢复 readonly。
        camera_combo = getattr(self, "camera_combo", None)
        if camera_combo is not None:
            try:
                if running:
                    camera_combo.configure(state="disabled")
                elif self._camera_entries:
                    camera_combo.configure(state="readonly")
            except Exception:
                pass

        # 第二摄像头下拉：与主摄像头下拉同步禁用/恢复（issue #57）。
        camera_combo_2 = getattr(self, "camera_combo_2", None)
        if camera_combo_2 is not None:
            try:
                if running:
                    camera_combo_2.configure(state="disabled")
                elif self._camera_entries:
                    camera_combo_2.configure(state="readonly")
            except Exception:
                pass

        # 刷新控件：复用既有联动（枚举中 / 运行中禁用）。
        self._set_refresh_enabled()

        # Model_Selector：运行中禁用、未运行恢复 readonly。
        model_combo = getattr(self, "model_combo", None)
        if model_combo is not None:
            try:
                model_combo.configure(state="disabled" if running else "readonly")
            except Exception:
                pass

        # Record_Toggle：运行中启用并置「开始录制」；未运行禁用。
        record_btn = getattr(self, "record_btn", None)
        if record_btn is not None:
            try:
                if running:
                    record_btn.configure(state="normal", text=RECORD_BTN_TEXT["idle"])
                else:
                    record_btn.configure(state="disabled")
            except Exception:
                pass

        # 「结束录制」：会话开始时尚无录制片段，故初始禁用；未运行同样禁用。
        # 录制开始后由 _on_record_toggle / _refresh_recording_status 联动启用。
        sync_record_stop = getattr(self, "_sync_record_stop_enabled", None)
        if sync_record_stop is not None:
            sync_record_stop("idle")

        # Compare_Control：始终 enabled。
        compare_btn = getattr(self, "compare_btn", None)
        if compare_btn is not None:
            try:
                compare_btn.configure(state="normal")
            except Exception:
                pass

        # Start_Control / stop_btn：兼容现有分离双按钮的同时切换 start_btn 文本。
        start_btn = getattr(self, "start_btn", None)
        if start_btn is not None:
            try:
                if running:
                    start_btn.configure(state="disabled", text="停止")
                else:
                    start_btn.configure(state="normal", text="开始")
            except Exception:
                pass
        stop_btn = getattr(self, "stop_btn", None)
        if stop_btn is not None:
            try:
                stop_btn.configure(state="normal" if running else "disabled")
            except Exception:
                pass

        # Status_Area：未运行显示「就绪」（需求 4.5）。
        if not running:
            self.status_var.set("就绪")

    # ---- 摄像头枚举与选择 ----

    def _set_refresh_enabled(self) -> None:
        """仅当非枚举中且采集未运行时启用刷新控件（需求 5.3、5.7）。"""
        running = bool(self._worker and self._worker.is_alive())
        enabled = (not self._enum_busy.is_set()) and (not running)
        try:
            self.refresh_btn.configure(state="normal" if enabled else "disabled")
        except Exception:
            pass

    def _start_enumeration(self) -> None:
        """在后台线程枚举可用摄像头，结果经 root.after 回写 UI（需求 1.1、5.2）。"""
        if self._enum_busy.is_set():
            return
        self._enum_busy.set()
        self._set_refresh_enabled()
        self.camera_combo.configure(state="disabled")
        self.camera_choice_var.set("正在检测摄像头…")

        def _run() -> None:
            ok = True
            entries: list[CameraEntry] = []
            try:
                entries = enumerate_cameras()
            except Exception:
                ok = False
            self.root.after(0, lambda: self._apply_camera_entries(entries, ok))

        threading.Thread(target=_run, daemon=True).start()

    def _apply_camera_entries(self, entries: list[CameraEntry], ok: bool) -> None:
        """枚举回调（主线程）：重建下拉项并更新输入源状态。

        需求 1.8、2.2、2.5、2.6、5.4、5.5、5.6。
        """
        try:
            if not ok:
                # 探测失败/超时：保留刷新前的列表与下拉项不变（需求 5.6）。
                self.status_var.set("刷新摄像头失败，已保留原有列表。")
                if self._camera_entries:
                    self.camera_combo.configure(state="readonly")
                return

            self._camera_entries = list(entries)
            if not entries:
                # 空列表：禁用下拉并提示，不记录输入源（需求 1.8、2.6、5.5）。
                self.camera_combo.configure(values=[], state="disabled")
                self.camera_choice_var.set("")
                self.source_hint_var.set("未检测到可用摄像头")
                if self._source_state.kind == "camera":
                    self._source_state.clear()
                    self.source_var.set("")
                self.camera_combo_2.configure(values=[NO_SECOND_CAMERA], state="disabled")
                self.camera_choice_var_2.set(NO_SECOND_CAMERA)
                return

            labels = [e.label for e in entries]
            self.camera_combo.configure(values=labels, state="readonly")
            # 保留已选摄像头（若仍在列表中），否则默认选第一项（需求 2.5）。
            current = self.camera_choice_var.get()
            if current not in labels:
                current = labels[0]
            self.camera_choice_var.set(current)
            self._select_camera_by_label(current)

            # 第二摄像头下拉：同步为「无」+ 真实摄像头列表；已选项不在新列表中则回退「无」。
            labels_2 = [NO_SECOND_CAMERA] + labels
            self.camera_combo_2.configure(values=labels_2, state="readonly")
            current_2 = self.camera_choice_var_2.get()
            if current_2 not in labels_2:
                current_2 = NO_SECOND_CAMERA
            self.camera_choice_var_2.set(current_2)
        finally:
            self._enum_busy.clear()
            self._set_refresh_enabled()

    def _camera_index_for_label(self, label: str) -> int | None:
        """由显示文本反查摄像头编号，找不到返回 None。"""
        for e in self._camera_entries:
            if e.label == label:
                return e.index
        return None

    def _select_camera_by_label(self, label: str) -> None:
        """由显示文本反查编号并记录为摄像头输入源（需求 2.3、3.3）。"""
        index = self._camera_index_for_label(label)
        if index is not None:
            self._source_state.select_camera(index)
            self.source_var.set(str(index))
            self.source_hint_var.set(self._source_state.hint_text())

    def _on_camera_selected(self, event=None) -> None:
        self._select_camera_by_label(self.camera_choice_var.get())

    def _refresh_cameras(self) -> None:
        """刷新可用摄像头列表（需求 5.1、5.3、5.7）。"""
        if self._worker and self._worker.is_alive():
            return
        if self._enum_busy.is_set():
            return
        self._start_enumeration()

    def _collect_state(self) -> UiState:
        # 无有效输入源：使用统一提示文案（需求 4.2）。
        if self._source_state.kind == "none":
            raise ValueError("请先选择摄像头或视频")
        source = self.source_var.get().strip()
        if not source:
            raise ValueError("请先选择摄像头或视频")

        workers = clamp_workers(self.workers_var.get() or 1)

        # 第二摄像头（可选，双摄双面视图，issue #57）：未选或选不到真实条目 → source2=None，
        # 即今天的单摄行为不变。
        source2: str | None = None
        camera_choice_var_2 = getattr(self, "camera_choice_var_2", None)
        label_2 = camera_choice_var_2.get().strip() if camera_choice_var_2 is not None else ""
        if label_2 and label_2 != NO_SECOND_CAMERA:
            index_2 = self._camera_index_for_label(label_2)
            if index_2 is not None:
                if source.isdigit() and int(source) == index_2:
                    raise ValueError("两个摄像头不能选同一个")
                source2 = str(index_2)

        return UiState(
            source=source,
            pose_variant=self.pose_var.get().strip() or "full",
            workers=workers,
            enable_hands=bool(self.enable_hands_var.get()),
            out_path=(self.out_var.get().strip() or None) if bool(self.save_var.get()) else None,
            source2=source2,
        )

    def _start(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        try:
            state = self._collect_state()
        except Exception as e:
            messagebox.showerror("配置错误", str(e))
            return

        self._stop_evt.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self._set_refresh_enabled()
        self.status_var.set("启动中…（首次运行可能需要下载模型）")
        self.actions_var.set("-")
        self.progress_var.set(0.0)
        self.progress_text_var.set("")
        self.progress_bar.configure(mode="determinate", maximum=100.0, value=0.0)

        self._worker = threading.Thread(target=self._worker_loop, args=(state,), daemon=True)
        self._worker.start()
        # 集中刷新运行态控件（禁用 Camera/Model_Selector、启用 Record_Toggle 等，需求 4.3 等）。
        self._set_running_controls(True)

    def _stop(self) -> None:
        self._stop_evt.set()
        self.stop_btn.configure(state="disabled")
        self.status_var.set("正在停止…")

    def _on_close(self) -> None:
        self._stop_evt.set()
        self.root.after(50, self.root.destroy)

    def _worker_loop(self, state: UiState) -> None:
        source = state.source
        is_file = not source.isdigit()

        if source.isdigit():
            cap = open_camera(int(source))
        else:
            cap = cv2.VideoCapture(source)

        if not cap.isOpened():
            self._post_status(f"无法打开输入源：{source}")
            self._post_done()
            return

        src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        fps_for_ts = src_fps if (is_file and src_fps > 1e-3) else 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) if is_file else 0

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)

        if is_file and state.workers > 1:
            self._worker_loop_parallel_video(state, cap, fps_for_ts, total)
            return

        if (not is_file) and state.workers > 1:
            self._worker_loop_parallel_camera(state, cap, fps_for_ts)
            return

        # 录制由 RecordingController 管理：进入帧循环前登记本会话写入参数（fps/size）。
        self._rec.begin_session(fps=fps_for_ts, size=(w, h))

        try:
            try:
                models_dir_path = models_dir()
                pipe = MediaPipePipeline(
                    models_dir=models_dir_path,
                    cfg=PipelineConfig(
                        pose_variant=state.pose_variant,
                        running_mode="video",
                        enable_hands=state.enable_hands,
                    ),
                )
            except Exception as e:
                cap.release()
                self._post_status(f"初始化失败：{e}")
                self._post_done()
                return

            t0 = time.monotonic()
            frame_count = 0
            self._post_status("运行中…")
            self._post_progress(0, total)

            while not self._stop_evt.is_set():
                ok, frame = cap.read()
                if not ok:
                    # Video ended or camera read failed.
                    self._stop_evt.set()
                    break

                ts = pipe.next_timestamp_ms(is_file=is_file, fps_for_ts=fps_for_ts)
                annotated, actions = pipe.annotate(frame, timestamp_ms=ts)

                frame_count += 1
                if is_file and total > 0 and (frame_count % 5 == 0 or frame_count == total):
                    self._post_progress(frame_count, total)
                fps = frame_count / max(1e-6, (time.monotonic() - t0))
                cv2.putText(
                    annotated,
                    f"FPS: {fps:.1f}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    annotated,
                    "点击“停止”结束",
                    (10, annotated.shape[0] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

                self._rec.write_frame(annotated)

                if actions:
                    actions_text = ", ".join(ACTION_LABELS_ZH.get(a, a) for a in actions)
                else:
                    actions_text = "-"
                self._post_frame(annotated, actions_text)

            cap.release()
            cv2.destroyAllWindows()

            self._post_status("已停止")
            self._post_progress(frame_count, total)
            self._post_done()
        finally:
            # 覆盖正常结束 / 停止 / 异常：释放 writer 并复位录制状态。
            self._rec.close_session()

    def _worker_loop_parallel_video(
        self,
        state: UiState,
        cap: cv2.VideoCapture,
        fps_for_ts: float,
        total: int,
    ) -> None:
        # Parallel processing for offline videos using IMAGE mode pipelines.
        models_dir_path = models_dir()
        workers = max(1, int(state.workers))
        frame_q: "Queue[tuple[int, object] | None]" = Queue(maxsize=workers * 2)
        result_q: "Queue[tuple[int, object, list[str]]]" = Queue(maxsize=workers * 2)

        # 录制由 RecordingController 管理：进入帧循环前登记本会话写入参数（fps/size）。
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
        self._rec.begin_session(fps=fps_for_ts, size=(w, h))

        def reader() -> None:
            idx = 0
            while not self._stop_evt.is_set():
                ok, frame = cap.read()
                if not ok:
                    break
                frame_q.put((idx, frame))
                idx += 1
            for _ in range(workers):
                frame_q.put(None)

        def worker() -> None:
            pipe = MediaPipePipeline(
                models_dir=models_dir_path,
                cfg=PipelineConfig(
                    pose_variant=state.pose_variant,
                    running_mode="image",
                    enable_hands=state.enable_hands,
                ),
            )
            while True:
                item = frame_q.get()
                if item is None:
                    break
                if self._stop_evt.is_set():
                    continue
                idx, frame = item
                annotated, actions = pipe.annotate(frame, timestamp_ms=None)
                result_q.put((idx, annotated, actions))

        self._post_status(f"运行中…（离线多线程：{workers}）")
        self._post_progress(0, total)

        t_reader = threading.Thread(target=reader, daemon=True)
        t_reader.start()
        worker_ts = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
        for t in worker_ts:
            t.start()

        next_idx = 0
        pending: dict[int, tuple[object, list[str]]] = {}
        written = 0
        t0 = time.monotonic()

        try:
            while not self._stop_evt.is_set():
                if next_idx in pending:
                    annotated, actions = pending.pop(next_idx)
                    written += 1

                    self._rec.write_frame(annotated)

                    if total > 0 and (written % 5 == 0 or written == total):
                        self._post_progress(written, total)

                    fps = written / max(1e-6, (time.monotonic() - t0))
                    cv2.putText(
                        annotated,
                        f"FPS: {fps:.1f}",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (255, 255, 255),
                        2,
                        cv2.LINE_AA,
                    )

                    if actions:
                        actions_text = ", ".join(ACTION_LABELS_ZH.get(a, a) for a in actions)
                    else:
                        actions_text = "-"
                    self._post_frame(annotated, actions_text)
                    next_idx += 1
                    continue

                try:
                    idx, annotated, actions = result_q.get(timeout=0.2)
                except Exception:
                    alive = t_reader.is_alive() or any(t.is_alive() for t in worker_ts)
                    if (not alive) and (not pending):
                        break
                    continue

                pending[int(idx)] = (annotated, actions)

            self._stop_evt.set()
            t_reader.join(timeout=2.0)
            for t in worker_ts:
                t.join(timeout=2.0)

            cap.release()
            cv2.destroyAllWindows()

            self._post_status("已停止")
            self._post_progress(written, total)
            self._post_done()
        finally:
            # 覆盖正常结束 / 停止 / 异常：释放 writer 并复位录制状态。
            self._rec.close_session()

    def _worker_loop_parallel_camera(
        self,
        state: UiState,
        cap: cv2.VideoCapture,
        fps_for_ts: float,
    ) -> None:
        """实时摄像头多核并行推理（IMAGE 模式 + 满则丢帧）。

        单线程 VIDEO 模式在多核机上只用到少数核心，heavy 模型实时只能跑 ~15fps；并行多
        worker 能近线性提升吞吐。代价是失去 VIDEO 模式的时序平滑（骨架更抖），且高负载时
        丢弃新帧以约束端到端延迟。默认（线程数=1）仍走单线程 VIDEO 路径，行为不变。
        """
        workers = max(1, int(state.workers))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
        self._rec.begin_session(fps=fps_for_ts, size=(w, h))

        engine = ParallelPoseEngine(
            pipeline_factory=default_pipeline_factory(
                models_dir=models_dir(),
                pose_variant=state.pose_variant,
                enable_hands=state.enable_hands,
            ),
            workers=workers,
            drop_when_full=True,
        )

        try:
            try:
                engine.start()
            except Exception as e:
                cap.release()
                self._post_status(f"初始化失败：{e}")
                self._post_done()
                return

            def reader() -> None:
                try:
                    while not self._stop_evt.is_set():
                        ok, frame = cap.read()
                        if not ok:
                            break
                        engine.submit(frame)
                finally:
                    engine.signal_input_done()

            t_reader = threading.Thread(target=reader, daemon=True)
            t_reader.start()

            self._post_status(f"运行中…（实时多线程：{workers}，时序平滑关闭）")
            self._post_progress(0, 0)

            t0 = time.monotonic()
            rendered = 0
            while not self._stop_evt.is_set():
                res = engine.get(timeout=0.2)
                if res is None:
                    if engine.is_drained():
                        break
                    continue
                annotated = res.annotated
                rendered += 1
                fps = rendered / max(1e-6, (time.monotonic() - t0))
                cv2.putText(
                    annotated,
                    f"FPS: {fps:.1f} (x{workers})",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )

                self._rec.write_frame(annotated)

                if res.actions:
                    actions_text = ", ".join(ACTION_LABELS_ZH.get(a, a) for a in res.actions)
                else:
                    actions_text = "-"
                self._post_frame(annotated, actions_text)

            self._stop_evt.set()
            engine.close()
            t_reader.join(timeout=2.0)
            cap.release()
            cv2.destroyAllWindows()

            err = engine.take_error()
            if err is not None:
                self._post_status(f"推理失败：{err}")
            else:
                self._post_status("已停止")
            self._post_progress(0, 0)
            self._post_done()
        finally:
            engine.close()
            self._rec.close_session()

    def _post_frame(self, frame_bgr: np.ndarray, actions: str) -> None:
        # Keep only the latest frame.
        while True:
            try:
                self._queue.get_nowait()
            except Empty:
                break
        self._queue.put((frame_bgr, actions))

    def _post_status(self, text: str) -> None:
        # Tkinter updates must happen on the main thread.
        self.root.after(0, lambda: self.status_var.set(text))

    def _post_progress(self, done: int, total: int) -> None:
        def _set() -> None:
            if total > 0:
                self.progress_bar.configure(mode="determinate", maximum=float(total))
                self.progress_bar["value"] = float(done)
                pct = (done / total) * 100.0
                self.progress_text_var.set(f"进度：{done}/{total}（{pct:.1f}%）")
            else:
                # Unknown total (camera): show nothing.
                self.progress_bar.configure(mode="determinate", maximum=100.0)
                self.progress_bar["value"] = 0.0
                self.progress_text_var.set("")

        self.root.after(0, _set)

    def _post_done(self) -> None:
        def _done() -> None:
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self._set_refresh_enabled()
            # 会话结束：集中复位运行态控件并使 Status_Area 显示「就绪」（需求 4.5、5.1）。
            self._set_running_controls(False)

        self.root.after(0, _done)

    def _tick(self) -> None:
        # 录制状态刷新必须每 tick 执行，与帧队列是否有新帧无关（需求 5.9/5.10/5.11）。
        self._refresh_recording_status()

        try:
            frame_bgr, actions = self._queue.get_nowait()
        except Empty:
            self.root.after(30, self._tick)
            return

        self.actions_var.set(actions)

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)

        # Fit-to-window preview (keep aspect ratio).
        pw = max(1, self.preview.winfo_width())
        ph = max(1, self.preview.winfo_height())
        iw, ih = img.size
        scale = min(pw / iw, ph / ih)
        nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
        img = img.resize((nw, nh), Image.BILINEAR)

        self._photo = ImageTk.PhotoImage(img)
        self.preview.configure(image=self._photo)
        self.root.after(30, self._tick)


def main() -> None:
    root = Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
