"""감지 이벤트와 시간순 프레임 선택.
프레임 참조 경로를 버퍼에 저장하고 stop_required=True인 이벤트를 반환한다."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

from src.perception.event_gate import Gate


@dataclass(frozen=True)
class FrameRef:
    timestamp: float
    path: Path


@dataclass(frozen=True)
class HazardTrigger:
    category: str
    frames: tuple[Path, ...]
    stop_required: bool = True

    @property
    def vlm_ready(self) -> bool:
        """VLM 요청에 사용할 프레임이 있는지 확인한다."""
        return bool(self.frames)


class VLMTriggerBridge:
    """감지 게이트와 최근 프레임 버퍼를 연결한다."""

    def __init__(self, *, max_frames: int = 4, window_seconds: float = 2.0):
        if max_frames < 2 or window_seconds <= 0:
            raise ValueError("Invalid frame selection configuration")
        self.max_frames = max_frames
        self.window_seconds = window_seconds
        self.frames: deque[FrameRef] = deque(maxlen=128)
        self.gate = Gate(hits=2, misses=2)  # 예제의 감지 확인 횟수.
        self._fired = False

    def image_callback(self, timestamp: float, image_ref: str | Path) -> None:
        if self.frames and timestamp < self.frames[-1].timestamp:
            raise ValueError("Frame timestamps must be chronological")
        self.frames.append(FrameRef(timestamp, Path(image_ref)))

    def pick_frames(self, now: float) -> tuple[Path, ...]:
        """관측 구간에서 최대 N개 프레임을 균등한 간격으로 선택한다."""
        recent = [frame.path for frame in self.frames
                  if 0 <= now - frame.timestamp <= self.window_seconds]
        if len(recent) <= self.max_frames:
            return tuple(recent)
        n = len(recent) - 1
        return tuple(recent[round(i * n / (self.max_frames - 1))]
                     for i in range(self.max_frames))

    def trigger_callback(self, *, detected: bool, category: str,
                         now: float) -> HazardTrigger | None:
        """게이트 활성화 시 정지 권고와 선택한 프레임을 이벤트로 반환한다."""
        active = self.gate.update(detected)
        if not active:
            if not self.gate.active:
                self._fired = False
            return None
        if self._fired:
            return None
        frames = self.pick_frames(now)
        if not frames:
            # 프레임이 없어도 정지 권고를 반환한다.
            # 다음 프레임이 들어오면 다시 이벤트를 구성할 수 있게 유지한다.
            return HazardTrigger(category=category, frames=())
        self._fired = True
        return HazardTrigger(category=category, frames=frames)


if __name__ == "__main__":
    bridge = VLMTriggerBridge()
    for index in range(4):
        bridge.image_callback(index * 0.5, f"frame_{index}.jpg")
    assert bridge.trigger_callback(detected=True, category="PERSON", now=1.5) is None
    event = bridge.trigger_callback(detected=True, category="PERSON", now=1.5)
    assert event and event.stop_required and len(event.frames) == 4
    print("Stop-first candidate event:", event)
