# -*- coding: utf-8 -*-
"""Thread-safe, Tk-independent camera warmup support.

Each role owns at most one background reader. Readers continuously replace a
single latest-frame slot so callers can obtain a fresh pair without building a
frame history. Capture ownership can later be transferred atomically to the
normal processing worker with :meth:`CameraWarmupPool.claim_pair`.
"""
from __future__ import annotations

import inspect
import threading
import time
from dataclasses import dataclass, field
from numbers import Integral
from typing import Any, Callable, Final

import numpy as np

from apps.camera_enum import open_camera


PRIMARY: Final = "primary"
SECONDARY: Final = "secondary"
ROLES: Final = (PRIMARY, SECONDARY)

CaptureFactory = Callable[[int], Any]


class CameraWarmupError(RuntimeError):
    """Base error raised by :class:`CameraWarmupPool`."""


class CameraWarmupTimeout(CameraWarmupError, TimeoutError):
    """The requested camera pair did not become ready before its deadline."""


class CameraWarmupStopped(CameraWarmupError):
    """The caller cancelled a wait through its stop event."""


@dataclass(frozen=True)
class WarmFrame:
    """Latest valid frame captured for one camera role."""

    frame: np.ndarray
    captured_at: float
    sequence: int
    generation: int


@dataclass
class _WarmupSlot:
    role: str
    index: int
    generation: int
    stop_event: threading.Event = field(default_factory=threading.Event)
    cap: Any | None = None
    latest: WarmFrame | None = None
    error: BaseException | None = None
    thread: threading.Thread | None = None
    claim_token: object | None = None
    sequence: int = 0
    release_lock: threading.Lock = field(default_factory=threading.Lock)
    released: bool = False
    reaper_started: bool = False

    @property
    def claimed(self) -> bool:
        return self.claim_token is not None


class CameraWarmupPool:
    """Maintain latest-only background readers for a two-camera pair."""

    def __init__(
        self,
        capture_factory: CaptureFactory | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        stop_poll_interval: float = 0.02,
        join_timeout: float = 1.0,
    ) -> None:
        self._capture_factory = capture_factory or open_camera
        self._factory_accepts_stop_event = self._supports_stop_event(
            self._capture_factory
        )
        self._clock = clock
        self._stop_poll_interval = max(0.001, float(stop_poll_interval))
        self._join_timeout = max(0.0, float(join_timeout))
        self._condition = threading.Condition(threading.RLock())
        self._slots: dict[str, _WarmupSlot | None] = {
            PRIMARY: None,
            SECONDARY: None,
        }
        self._generations = {PRIMARY: 0, SECONDARY: 0}
        self._retired: dict[int, _WarmupSlot] = {}
        self._closed = False

    def warm(self, role: str, index: int) -> None:
        """Schedule warming; the reader waits for any old device owner to exit."""

        role = self._validate_role(role)
        index = self._validate_index(index)
        previous: _WarmupSlot | None = None
        failed_slot: _WarmupSlot | None = None
        start_error: BaseException | None = None

        with self._condition:
            self._ensure_open()
            current = self._slots[role]
            if current is not None and current.claimed:
                raise CameraWarmupError(
                    f"{role} camera is being claimed and cannot be replaced"
                )
            if (
                current is not None
                and current.index == index
                and current.error is None
                and not current.stop_event.is_set()
                and not current.claimed
            ):
                return
            other_role = SECONDARY if role == PRIMARY else PRIMARY
            other = self._slots[other_role]
            if other is not None and other.index == index:
                raise ValueError(
                    "the same camera index cannot be warmed for both roles"
                )

            previous = current
            if previous is not None:
                self._retire_locked(previous)

            slot = self._new_slot_locked(role, index)
            self._slots[role] = slot
            try:
                slot.thread.start()
            except BaseException as exc:
                start_error = exc
                failed_slot = slot
                self._slots[role] = None
                self._generations[role] += 1
                self._retire_locked(slot)
            self._condition.notify_all()

        # Do not wait for an old, possibly blocked device open. Its generation
        # is already detached, so it cannot publish and will release on return.
        if previous is not None:
            self._interrupt_slot(previous, join=False)
            self._reap_slot_async(previous)
        if failed_slot is not None:
            self._interrupt_slot(failed_slot, join=False)
            self._reap_slot_async(failed_slot)
        if start_error is not None:
            raise CameraWarmupError(
                f"failed to start {role} camera warmup reader"
            ) from start_error

    def cancel(self, role: str) -> None:
        """Cancel one role and release any capture it currently owns."""

        role = self._validate_role(role)
        with self._condition:
            slot = self._slots[role]
            if slot is None:
                return
            self._slots[role] = None
            self._generations[role] += 1
            slot.claim_token = None
            self._retire_locked(slot)
            self._condition.notify_all()
        self._interrupt_slot(slot, join=False)
        self._reap_slot_async(slot)

    def wait_pair(
        self,
        primary_index: int,
        secondary_index: int,
        *,
        timeout: float,
        stop_event: threading.Event,
    ) -> tuple[WarmFrame, WarmFrame]:
        """Wait until both roles have valid frames.

        Missing roles are started concurrently, after any old owner releases
        that device. The timeout includes this drain. Any error, timeout, stop,
        or role replacement cancels only the pair observed by this call.
        """

        primary_index, secondary_index = self._validate_pair(
            primary_index, secondary_index
        )
        timeout = self._validate_timeout(timeout)
        if not hasattr(stop_event, "is_set"):
            raise TypeError("stop_event must provide is_set()")
        if stop_event.is_set():
            raise CameraWarmupStopped("camera warmup was stopped")

        expected = self._warm_pair(primary_index, secondary_index)

        try:
            return self._wait_expected_pair(expected, timeout, stop_event)
        except BaseException:
            self._cancel_expected(expected, join=False)
            raise

    def snapshot_pair(
        self,
        primary_index: int,
        secondary_index: int,
        *,
        after: tuple[int, int] | None = None,
    ) -> tuple[WarmFrame, WarmFrame] | None:
        """Return the current pair if ready and newer than ``after``.

        ``after`` is a ``(primary_sequence, secondary_sequence)`` cursor. A new
        snapshot is returned when either role has advanced beyond its cursor.
        """

        primary_index, secondary_index = self._validate_pair(
            primary_index, secondary_index
        )
        cursor = self._validate_after(after)
        with self._condition:
            pair = self._matching_pair(primary_index, secondary_index)
            if pair is None:
                return None
            primary, secondary = pair
            if (
                primary.claimed
                or secondary.claimed
                or primary.error is not None
                or secondary.error is not None
                or primary.latest is None
                or secondary.latest is None
            ):
                return None
            result = (primary.latest, secondary.latest)
            if cursor is not None and (
                result[0].sequence <= cursor[0]
                and result[1].sequence <= cursor[1]
            ):
                return None
            return result

    def claim_pair(
        self,
        primary_index: int,
        secondary_index: int,
        *,
        timeout: float,
        expected_generations: tuple[int, int] | None = None,
        stop_event: threading.Event | None = None,
    ) -> tuple[Any, Any]:
        """Stop existing ready readers and atomically transfer their captures.

        ``claim_pair`` never starts or replaces readers. Callers must first use
        :meth:`wait_pair` and may bind the claim to the returned frame
        generations. The timeout covers reader shutdown only. If either capture
        cannot be transferred, both are released and no partial result escapes.
        """

        primary_index, secondary_index = self._validate_pair(
            primary_index, secondary_index
        )
        timeout = self._validate_timeout(timeout)
        generations = self._validate_generations(expected_generations)
        if stop_event is not None and not hasattr(stop_event, "is_set"):
            raise TypeError("stop_event must provide is_set()")
        if stop_event is not None and stop_event.is_set():
            raise CameraWarmupStopped("camera warmup was stopped")
        deadline = self._clock() + timeout

        with self._condition:
            expected = self._matching_pair(primary_index, secondary_index)
            if expected is None:
                raise CameraWarmupError(
                    "camera warmup pair is not ready for claim"
                )
            primary, secondary = expected
            if generations is not None and (
                primary.generation,
                secondary.generation,
            ) != generations:
                raise CameraWarmupError(
                    "camera warmup pair generation changed before claim"
                )
            if stop_event is not None and stop_event.is_set():
                raise CameraWarmupStopped("camera warmup was stopped")
            if not self._slots_ready_for_claim(expected):
                self._condition.notify_all()
                claim_error = CameraWarmupError(
                    "camera warmup pair is not transferable"
                )
            else:
                claim_error = None
                claim_token = object()
                primary.claim_token = claim_token
                secondary.claim_token = claim_token
                primary.stop_event.set()
                secondary.stop_event.set()
                self._condition.notify_all()

        if claim_error is not None:
            self._cancel_expected(expected, join=False)
            raise claim_error

        try:
            for slot in expected:
                thread = slot.thread
                if thread is None:
                    raise CameraWarmupError(
                        f"{slot.role} camera reader was not started"
                    )
                while thread.is_alive():
                    if stop_event is not None and stop_event.is_set():
                        raise CameraWarmupStopped("camera warmup was stopped")
                    remaining = deadline - self._clock()
                    if remaining <= 0:
                        raise CameraWarmupTimeout(
                            "timed out stopping camera readers"
                        )
                    thread.join(min(remaining, self._stop_poll_interval))

            with self._condition:
                if stop_event is not None and stop_event.is_set():
                    raise CameraWarmupStopped("camera warmup was stopped")
                current = self._matching_pair(primary_index, secondary_index)
                if (
                    current is None
                    or current[0] is not primary
                    or current[1] is not secondary
                    or self._closed
                    or not self._slots_completed_claim(expected, claim_token)
                ):
                    raise CameraWarmupError(
                        "camera warmup pair changed while being claimed"
                    )
                cap_primary = primary.cap
                cap_secondary = secondary.cap
                self._slots[PRIMARY] = None
                self._slots[SECONDARY] = None
                self._generations[PRIMARY] += 1
                self._generations[SECONDARY] += 1
                primary.cap = None
                secondary.cap = None
                primary.claim_token = None
                secondary.claim_token = None
                self._condition.notify_all()
            return cap_primary, cap_secondary
        except BaseException:
            self._abort_claim(expected, claim_token)
            raise

    def close(self) -> None:
        """Stop every reader and permanently release pool-owned captures."""

        with self._condition:
            if self._closed:
                slots = list(self._retired.values())
            else:
                self._closed = True
                slots = [slot for slot in self._slots.values() if slot is not None]
                for role in ROLES:
                    self._slots[role] = None
                    self._generations[role] += 1
                for slot in slots:
                    slot.claim_token = None
                    self._retire_locked(slot)
            slots = list({id(slot): slot for slot in [*slots, *self._retired.values()]}.values())
            self._condition.notify_all()
        self._interrupt_slots(slots, timeout=self._join_timeout)

    def __enter__(self) -> "CameraWarmupPool":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _reader_loop(self, slot: _WarmupSlot) -> None:
        cap: Any | None = None
        preserve_for_claim = False
        try:
            cap = self._open_capture(slot)
            if cap is None:
                raise CameraWarmupError(
                    f"{slot.role} camera {slot.index} returned no capture"
                )
            is_opened = getattr(cap, "isOpened", None)
            if callable(is_opened) and not bool(is_opened()):
                raise CameraWarmupError(
                    f"{slot.role} camera {slot.index} could not be opened"
                )

            with self._condition:
                if not self._slot_is_current(slot) or slot.stop_event.is_set():
                    return
                slot.cap = cap
                self._condition.notify_all()

            while not slot.stop_event.is_set():
                ok, frame = cap.read()
                if slot.stop_event.is_set():
                    break
                if not ok or not self._valid_frame(frame):
                    raise CameraWarmupError(
                        f"{slot.role} camera {slot.index} failed to read a frame"
                    )
                captured_at = self._clock()
                with self._condition:
                    if not self._slot_is_current(slot) or slot.stop_event.is_set():
                        break
                    slot.sequence += 1
                    slot.latest = WarmFrame(
                        frame=frame,
                        captured_at=captured_at,
                        sequence=slot.sequence,
                        generation=slot.generation,
                    )
                    self._condition.notify_all()
        except BaseException as exc:
            with self._condition:
                if self._slot_is_current(slot):
                    slot.error = self._normalize_error(slot, exc)
                    slot.stop_event.set()
                    self._condition.notify_all()
        finally:
            with self._condition:
                preserve_for_claim = (
                    cap is not None
                    and self._slot_is_current(slot)
                    and slot.claimed
                    and slot.cap is cap
                )
                if not preserve_for_claim and slot.cap is cap:
                    slot.cap = None
                self._condition.notify_all()
            released = True
            if cap is not None and not preserve_for_claim:
                released = self._release_once(slot, cap)
            if not preserve_for_claim:
                with self._condition:
                    if released:
                        self._retired.pop(id(slot), None)
                    else:
                        self._retired[id(slot)] = slot
                    self._condition.notify_all()

    def _wait_expected_pair(
        self,
        expected: tuple[_WarmupSlot, _WarmupSlot],
        timeout: float,
        stop_event: threading.Event,
    ) -> tuple[WarmFrame, WarmFrame]:
        deadline = self._clock() + timeout
        with self._condition:
            while True:
                if stop_event.is_set():
                    raise CameraWarmupStopped("camera warmup was stopped")
                if self._closed:
                    raise CameraWarmupError("camera warmup pool is closed")
                if not self._expected_is_current(expected):
                    raise CameraWarmupError("camera warmup pair was replaced")

                primary, secondary = expected
                for slot in expected:
                    if slot.claimed:
                        raise CameraWarmupError(
                            "camera warmup pair is already being claimed"
                        )
                    if slot.error is not None:
                        raise CameraWarmupError(str(slot.error)) from slot.error
                if primary.latest is not None and secondary.latest is not None:
                    return primary.latest, secondary.latest

                remaining = deadline - self._clock()
                if remaining <= 0:
                    retiring = [
                        str(slot.index) for slot in expected
                        if self._index_is_retiring_locked(slot.index)
                    ]
                    detail = (
                        f"; 摄像头 {', '.join(retiring)} 的上次采集仍未释放"
                        if retiring else ""
                    )
                    raise CameraWarmupTimeout(
                        "timed out waiting for both cameras to warm" + detail
                    )
                self._condition.wait(
                    min(remaining, self._stop_poll_interval)
                )

    def _cancel_expected(
        self,
        expected: tuple[_WarmupSlot, _WarmupSlot],
        *,
        join: bool,
    ) -> None:
        retired: list[_WarmupSlot] = []
        with self._condition:
            for slot in expected:
                if self._slots[slot.role] is slot:
                    self._slots[slot.role] = None
                    self._generations[slot.role] += 1
                    slot.claim_token = None
                    self._retire_locked(slot)
                    retired.append(slot)
            self._condition.notify_all()
        if join:
            self._interrupt_slots(retired, timeout=self._join_timeout)
        else:
            for slot in retired:
                self._interrupt_slot(slot, join=False)
                self._reap_slot_async(slot)

    def _abort_claim(
        self,
        expected: tuple[_WarmupSlot, _WarmupSlot],
        claim_token: object,
    ) -> None:
        retired: list[_WarmupSlot] = []
        with self._condition:
            for slot in expected:
                if slot.claim_token is claim_token:
                    slot.claim_token = None
                if self._slots[slot.role] is slot:
                    self._slots[slot.role] = None
                    self._generations[slot.role] += 1
                    self._retire_locked(slot)
                    retired.append(slot)
            self._condition.notify_all()
        # The claim deadline is already exhausted or the transaction failed.
        # Completed readers can be released now; blocked readers release their
        # own capture after open/read returns and observes the detached slot.
        for slot in retired:
            self._interrupt_slot(slot, join=False)
            self._reap_slot_async(slot)

    def _retire_locked(self, slot: _WarmupSlot) -> None:
        slot.stop_event.set()
        self._retired[id(slot)] = slot

    def _release_once(self, slot: _WarmupSlot, cap: Any) -> bool:
        with slot.release_lock:
            if slot.released:
                return True
            try:
                cap.release()
            except Exception as exc:
                with self._condition:
                    slot.error = CameraWarmupError(
                        f"{slot.role} camera {slot.index} release failed: {exc}"
                    )
                    if slot.cap is None:
                        slot.cap = cap
                    self._retired[id(slot)] = slot
                    self._condition.notify_all()
                return False
            slot.released = True
        with self._condition:
            if slot.cap is cap:
                slot.cap = None
            self._condition.notify_all()
        return True

    def _request_capture_interrupt(self, slot: _WarmupSlot) -> None:
        with self._condition:
            cap = slot.cap
        interrupt = getattr(cap, "interrupt", None) if cap is not None else None
        if callable(interrupt):
            try:
                interrupt()
            except Exception:
                pass

    def _interrupt_slot(self, slot: _WarmupSlot, *, join: bool) -> None:
        slot.stop_event.set()
        thread = slot.thread
        if (
            join
            and thread is not None
            and thread is not threading.current_thread()
            and thread.is_alive()
        ):
            thread.join(self._join_timeout)

        if thread is not None and thread.is_alive():
            self._request_capture_interrupt(slot)
            if join and thread is not threading.current_thread():
                thread.join(self._join_timeout)

        # Never release a capture while its owner thread may still be inside
        # open/read. A detached late reader releases it in _reader_loop.finally.
        if thread is None or not thread.is_alive():
            with self._condition:
                cap = slot.cap
            if cap is not None:
                released = self._release_once(slot, cap)
            else:
                released = True
            if released:
                with self._condition:
                    self._retired.pop(id(slot), None)

    def _reap_slot_async(self, slot: _WarmupSlot) -> None:
        """Finish a cancelled slot without blocking a UI caller."""

        with self._condition:
            if slot.reaper_started:
                return
            slot.reaper_started = True

        def _reap() -> None:
            thread = slot.thread
            if (
                thread is not None
                and thread is not threading.current_thread()
                and thread.is_alive()
            ):
                thread.join(self._join_timeout)
            if thread is not None and thread.is_alive():
                self._request_capture_interrupt(slot)
                thread.join(self._join_timeout)
            self._interrupt_slot(slot, join=False)

        reaper = threading.Thread(
            target=_reap,
            name=f"camera-warmup-reaper-{slot.role}-{slot.generation}",
            daemon=True,
        )
        try:
            reaper.start()
        except BaseException:
            # Keep cancellation bounded. The reader remains the only owner
            # allowed to release a native capture after open/read returns.
            self._interrupt_slot(slot, join=True)

    def _interrupt_slots(
        self, slots: list[_WarmupSlot], *, timeout: float
    ) -> None:
        deadline = self._clock() + max(0.0, timeout)
        for slot in slots:
            slot.stop_event.set()
            thread = slot.thread
            if (
                thread is not None
                and thread is not threading.current_thread()
                and thread.is_alive()
            ):
                thread.join(max(0.0, deadline - self._clock()))
        for slot in slots:
            thread = slot.thread
            if thread is not None and thread.is_alive():
                self._request_capture_interrupt(slot)
            self._interrupt_slot(slot, join=False)

    def _warm_pair(
        self, primary_index: int, secondary_index: int
    ) -> tuple[_WarmupSlot, _WarmupSlot]:
        desired = {PRIMARY: primary_index, SECONDARY: secondary_index}
        previous: list[_WarmupSlot] = []
        rollback: list[_WarmupSlot] = []
        created: list[_WarmupSlot] = []
        start_error: BaseException | None = None
        expected: tuple[_WarmupSlot, _WarmupSlot] | None = None

        with self._condition:
            self._ensure_open()
            if any(
                slot is not None and slot.claimed
                for slot in self._slots.values()
            ):
                raise CameraWarmupError(
                    "camera warmup pair is being claimed and cannot be replaced"
                )
            for role in ROLES:
                current = self._slots[role]
                reusable = (
                    current is not None
                    and current.index == desired[role]
                    and current.error is None
                    and not current.stop_event.is_set()
                    and not current.claimed
                )
                if reusable:
                    continue
                if current is not None:
                    self._retire_locked(current)
                    previous.append(current)
                slot = self._new_slot_locked(role, desired[role])
                self._slots[role] = slot
                created.append(slot)

            for slot in created:
                try:
                    slot.thread.start()
                except BaseException as exc:
                    start_error = exc
                    for rollback_role in ROLES:
                        current = self._slots[rollback_role]
                        if current is None:
                            continue
                        self._slots[rollback_role] = None
                        self._generations[rollback_role] += 1
                        self._retire_locked(current)
                        rollback.append(current)
                    break
            self._condition.notify_all()
            if start_error is None:
                expected = self._matching_pair(primary_index, secondary_index)
                if expected is None:  # pragma: no cover - protected by the lock
                    raise CameraWarmupError("could not establish camera warmup pair")

        for slot in previous:
            self._interrupt_slot(slot, join=False)
            self._reap_slot_async(slot)
        for slot in rollback:
            self._interrupt_slot(slot, join=False)
            self._reap_slot_async(slot)
        if start_error is not None:
            raise CameraWarmupError(
                "failed to start camera warmup pair reader"
            ) from start_error
        if expected is None:  # pragma: no cover - guarded above
            raise CameraWarmupError("could not establish camera warmup pair")
        return expected

    def _open_capture(self, slot: _WarmupSlot) -> Any:
        # cancel() is intentionally asynchronous. Mode switches, retries and
        # role swaps must drain the old owner before touching the same device.
        # Wait in this reader, never in the Tk caller or under a device lock.
        with self._condition:
            while True:
                if slot.stop_event.is_set() or not self._slot_is_current(slot):
                    raise CameraWarmupStopped("camera warmup was stopped")
                if not self._index_is_retiring_locked(slot.index):
                    break
                self._condition.wait(self._stop_poll_interval)
        if self._factory_accepts_stop_event:
            return self._capture_factory(
                slot.index, stop_event=slot.stop_event
            )
        return self._capture_factory(slot.index)

    def _index_is_retiring_locked(self, index: int) -> bool:
        for slot in self._retired.values():
            if slot.index != index or slot.released:
                continue
            thread = slot.thread
            if (thread is not None and thread.is_alive()) or slot.cap is not None:
                return True
        return False

    def _new_slot_locked(self, role: str, index: int) -> _WarmupSlot:
        self._generations[role] += 1
        slot = _WarmupSlot(
            role=role,
            index=index,
            generation=self._generations[role],
        )
        slot.thread = threading.Thread(
            target=self._reader_loop,
            args=(slot,),
            name=f"camera-warmup-{role}-{slot.generation}",
            daemon=True,
        )
        return slot

    def _matching_pair(
        self, primary_index: int, secondary_index: int
    ) -> tuple[_WarmupSlot, _WarmupSlot] | None:
        primary = self._slots[PRIMARY]
        secondary = self._slots[SECONDARY]
        if (
            primary is None
            or secondary is None
            or primary.index != primary_index
            or secondary.index != secondary_index
        ):
            return None
        return primary, secondary

    def _expected_is_current(
        self, expected: tuple[_WarmupSlot, _WarmupSlot]
    ) -> bool:
        return (
            self._slots[PRIMARY] is expected[0]
            and self._slots[SECONDARY] is expected[1]
        )

    def _slot_is_current(self, slot: _WarmupSlot) -> bool:
        return not self._closed and self._slots[slot.role] is slot

    @staticmethod
    def _slots_ready_for_claim(
        slots: tuple[_WarmupSlot, _WarmupSlot]
    ) -> bool:
        return all(
            slot.error is None
            and slot.cap is not None
            and slot.latest is not None
            and slot.thread is not None
            and slot.thread.is_alive()
            and not slot.stop_event.is_set()
            and not slot.claimed
            for slot in slots
        )

    @staticmethod
    def _slots_completed_claim(
        slots: tuple[_WarmupSlot, _WarmupSlot], claim_token: object
    ) -> bool:
        return all(
            slot.error is None
            and slot.cap is not None
            and slot.latest is not None
            and slot.thread is not None
            and not slot.thread.is_alive()
            and slot.claim_token is claim_token
            for slot in slots
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise CameraWarmupError("camera warmup pool is closed")

    @staticmethod
    def _validate_role(role: str) -> str:
        if role not in ROLES:
            raise ValueError(f"role must be one of {ROLES!r}")
        return role

    @staticmethod
    def _validate_index(index: int) -> int:
        if isinstance(index, bool) or not isinstance(index, Integral):
            raise ValueError("camera index must be a non-negative integer")
        normalized = int(index)
        if normalized < 0:
            raise ValueError("camera index must be a non-negative integer")
        return normalized

    def _validate_pair(
        self, primary_index: int, secondary_index: int
    ) -> tuple[int, int]:
        primary = self._validate_index(primary_index)
        secondary = self._validate_index(secondary_index)
        if primary == secondary:
            raise ValueError("primary and secondary cameras must be different")
        return primary, secondary

    @staticmethod
    def _validate_timeout(timeout: float) -> float:
        try:
            normalized = float(timeout)
        except (TypeError, ValueError) as exc:
            raise ValueError("timeout must be a non-negative number") from exc
        if normalized < 0:
            raise ValueError("timeout must be a non-negative number")
        return normalized

    @staticmethod
    def _validate_after(
        after: tuple[int, int] | None,
    ) -> tuple[int, int] | None:
        if after is None:
            return None
        if not isinstance(after, tuple) or len(after) != 2:
            raise ValueError("after must be a two-item sequence cursor")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in after):
            raise ValueError("after must contain integer sequences")
        return after

    @staticmethod
    def _validate_generations(
        generations: tuple[int, int] | None,
    ) -> tuple[int, int] | None:
        if generations is None:
            return None
        if not isinstance(generations, tuple) or len(generations) != 2:
            raise ValueError("expected_generations must be a two-item tuple")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in generations
        ):
            raise ValueError(
                "expected_generations must contain positive integers"
            )
        return generations

    @staticmethod
    def _valid_frame(frame: Any) -> bool:
        if frame is None:
            return False
        try:
            return int(getattr(frame, "size", 0)) > 0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _supports_stop_event(factory: CaptureFactory) -> bool:
        try:
            parameters = inspect.signature(factory).parameters.values()
        except (TypeError, ValueError):
            return False
        return any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            or (
                parameter.name == "stop_event"
                and parameter.kind
                in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY,
                )
            )
            for parameter in parameters
        )

    @staticmethod
    def _normalize_error(slot: _WarmupSlot, exc: BaseException) -> BaseException:
        if isinstance(exc, CameraWarmupError):
            return exc
        return CameraWarmupError(
            f"{slot.role} camera {slot.index} failed: {exc}"
        )


__all__ = [
    "CameraWarmupError",
    "CameraWarmupPool",
    "CameraWarmupStopped",
    "CameraWarmupTimeout",
    "PRIMARY",
    "SECONDARY",
    "WarmFrame",
]
