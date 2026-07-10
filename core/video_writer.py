from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import cv2

FFMPEG_TRANSCODE_TIMEOUT_S = 30 * 60


def _fourcc(code: str) -> int:
    return cv2.VideoWriter_fourcc(*code)


def open_video_writer(preferred_path: Path, *, fps: float, size: tuple[int, int]) -> tuple[cv2.VideoWriter, Path, str]:
    """
    Open a VideoWriter with best-effort codec/container compatibility.

    Returns: (writer, actual_path, codec_tag)
    """
    w, h = int(size[0]), int(size[1])
    if w <= 0 or h <= 0:
        raise ValueError(f"Invalid frame size: {size}")

    fps = float(fps) if fps and fps > 1e-6 else 30.0
    p = Path(preferred_path)
    suf = p.suffix.lower()

    candidates: list[tuple[Path, str]] = []
    if suf == ".mp4":
        # H.264 is widely supported, but may be unavailable in some OpenCV builds.
        # Keep every non-H.264 fallback in AVI so it can be transcoded reliably.
        avi_path = p.with_suffix(".avi")
        candidates = [
            (p, "avc1"),
            (p, "H264"),
            (avi_path, "MJPG"),
            (avi_path, "XVID"),
        ]
    elif suf == ".avi":
        candidates = [(p, "MJPG"), (p, "XVID")]
    else:
        # Unknown containers are not safe codec signals; normalize fallbacks to AVI.
        avi_path = p.with_suffix(".avi")
        candidates = [(avi_path, "MJPG"), (avi_path, "XVID")]

    last_err: str | None = None
    for out_path, codec in candidates:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        vw = cv2.VideoWriter(str(out_path), _fourcc(codec), fps, (w, h))
        if vw.isOpened():
            return vw, out_path, codec
        vw.release()
        last_err = f"VideoWriter open failed: path={out_path}, codec={codec}"

    raise RuntimeError(last_err or "VideoWriter open failed")


def transcode_to_h264(src: Path | None) -> Path | None:
    """Transcode an AVI recording to H.264 MP4 without risking the source."""
    if src is None:
        return None

    src = Path(src)
    if not src.exists() or src.suffix.lower() != ".avi":
        return src

    dst = src.with_suffix(".mp4")
    if dst == src:
        return src

    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{dst.stem}.",
            suffix=".tmp.mp4",
            dir=dst.parent,
            delete=False,
        ) as temporary_file:
            temporary_dst = Path(temporary_file.name)
    except OSError:
        return src

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        str(temporary_dst),
    ]
    try:
        subprocess.run(command, check=True, timeout=FFMPEG_TRANSCODE_TIMEOUT_S)
        if not temporary_dst.is_file() or temporary_dst.stat().st_size <= 0:
            raise OSError("ffmpeg produced no output")
        temporary_dst.replace(dst)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        try:
            temporary_dst.unlink(missing_ok=True)
        except OSError:
            pass
        return src

    try:
        src.unlink()
    except OSError:
        pass
    return dst
