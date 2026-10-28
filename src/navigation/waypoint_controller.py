"""웨이포인트 추종의 TURN·GO·FACE·WAIT 상태 전이.
실행: python -m src.navigation.waypoint_controller"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Phase(str, Enum):
    IDLE = "IDLE"
    TURN = "TURN"
    GO = "GO"
    FACE = "FACE"
    WAIT = "WAIT"
    DONE = "DONE"


@dataclass(frozen=True)
class Feedback:
    heading_aligned: bool = False
    waypoint_reached: bool = False
    final_heading_aligned: bool = False
    dwell_complete: bool = False


class WaypointFollower:
    """계획 경로와 도착 피드백으로 주행 상태 및 다음 경유점을 관리한다."""

    def __init__(self) -> None:
        self.phase = Phase.IDLE
        self.path: tuple[str, ...] = ()
        self.index = 0
        self.stops: set[int] = set()
        self.safety_stop = False
        self.operator_hold = False

    def on_path(self, nodes: list[str], stop_indices: set[int] | None = None) -> None:
        """계획 경로를 설정한다. 인덱스 0은 현재 위치다."""
        if len(nodes) < 2 or any(not node for node in nodes):
            raise ValueError("Example requires a route with at least two named nodes")
        proposed_stops = set(stop_indices) if stop_indices is not None else set()
        if any(type(i) is not int or i < 1 or i >= len(nodes)
               for i in proposed_stops):
            raise ValueError("Stop indices must refer to destination waypoints")
        # 경로와 정차 지점을 모두 검증한 뒤 상태를 변경한다.
        self.path = tuple(nodes)
        self.index = 1
        self.stops = proposed_stops
        self.phase = Phase.TURN

    def on_safety_stop(self, active: bool) -> None:
        self.safety_stop = bool(active)

    def on_operator_hold(self, active: bool) -> None:
        self.operator_hold = bool(active)

    def control(self, feedback: Feedback) -> str:
        """피드백에 따라 상태를 갱신하고 현재 상태명을 반환한다."""
        # 운영자 대기와 안전정지는 경로 진행보다 우선한다.
        # 대기 중에는 경유점 인덱스를 유지한다.
        if self.operator_hold:
            return "OPERATOR_HOLD"
        if self.safety_stop:
            return "SAFETY_STOP"
        if self.phase == Phase.TURN and feedback.heading_aligned:
            self.phase = Phase.GO
        elif self.phase == Phase.GO and feedback.waypoint_reached:
            if self.index in self.stops or self.index == len(self.path) - 1:
                self.phase = Phase.FACE
            else:
                self.index += 1
                self.phase = Phase.TURN
        elif self.phase == Phase.FACE and feedback.final_heading_aligned:
            self.phase = (Phase.DONE if self.index == len(self.path) - 1
                          else Phase.WAIT)
        elif self.phase == Phase.WAIT and feedback.dwell_complete:
            self.index += 1
            self.phase = Phase.TURN
        return self.phase.value


if __name__ == "__main__":
    follower = WaypointFollower()
    follower.on_path(["START", "A", "GOAL"], {1})
    for fb in (Feedback(heading_aligned=True), Feedback(waypoint_reached=True),
               Feedback(final_heading_aligned=True), Feedback(dwell_complete=True),
               Feedback(heading_aligned=True), Feedback(waypoint_reached=True),
               Feedback(final_heading_aligned=True)):
        print(follower.control(fb))
    assert follower.phase == Phase.DONE
