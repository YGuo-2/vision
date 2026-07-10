from __future__ import annotations

import subprocess
from pathlib import Path

from core import video_writer


def test_transcode_to_h264_runs_ffmpeg_and_removes_avi(
    tmp_path: Path, monkeypatch
) -> None:
    src = tmp_path / "recording.avi"
    src.write_bytes(b"avi")
    expected_dst = tmp_path / "recording.mp4"
    calls: list[tuple[list[str], bool]] = []

    def fake_run(command: list[str], *, check: bool):
        calls.append((command, check))
        expected_dst.write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(video_writer.subprocess, "run", fake_run)

    result = video_writer.transcode_to_h264(src)

    assert result == expected_dst
    assert not src.exists()
    assert expected_dst.exists()
    assert calls == [
        (
            [
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
                str(expected_dst),
            ],
            True,
        )
    ]


def test_transcode_to_h264_passes_through_none_missing_and_non_avi(
    tmp_path: Path, monkeypatch
) -> None:
    def unexpected_run(*_args, **_kwargs):
        raise AssertionError("ffmpeg must not run for pass-through inputs")

    monkeypatch.setattr(video_writer.subprocess, "run", unexpected_run)
    missing = tmp_path / "missing.avi"
    mp4 = tmp_path / "recording.mp4"
    mp4.write_bytes(b"mp4")

    assert video_writer.transcode_to_h264(None) is None
    assert video_writer.transcode_to_h264(missing) == missing
    assert video_writer.transcode_to_h264(mp4) == mp4


def test_transcode_to_h264_keeps_avi_when_ffmpeg_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    src = tmp_path / "recording.avi"
    src.write_bytes(b"avi")

    def missing_ffmpeg(*_args, **_kwargs):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(video_writer.subprocess, "run", missing_ffmpeg)

    assert video_writer.transcode_to_h264(src) == src
    assert src.exists()


def test_transcode_to_h264_keeps_avi_when_ffmpeg_fails(
    tmp_path: Path, monkeypatch
) -> None:
    src = tmp_path / "recording.avi"
    src.write_bytes(b"avi")

    def failed_ffmpeg(command, **_kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(video_writer.subprocess, "run", failed_ffmpeg)

    assert video_writer.transcode_to_h264(src) == src
    assert src.exists()


def test_transcode_to_h264_keeps_avi_when_ffmpeg_writes_no_output(
    tmp_path: Path, monkeypatch
) -> None:
    src = tmp_path / "recording.avi"
    src.write_bytes(b"avi")

    def successful_without_output(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(video_writer.subprocess, "run", successful_without_output)

    assert video_writer.transcode_to_h264(src) == src
    assert src.exists()
    assert not src.with_suffix(".mp4").exists()
