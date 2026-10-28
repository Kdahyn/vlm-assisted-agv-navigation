"""BEV 좌표 변환과 이동·회전 보정량을 제한한 오도메트리 오프셋 갱신."""
from __future__ import annotations

import math

Pose2D = tuple[float, float, float]  # (x, y, yaw 라디안)
Homography3 = tuple[tuple[float, float, float], ...]


def wrap_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def pixel_to_map(h: Homography3, point_px: tuple[float, float]) -> tuple[float, float]:
    """3×3 호모그래피의 동차좌표 나눗셈으로 픽셀을 지도 좌표로 변환한다."""
    if len(h) != 3 or any(len(row) != 3 for row in h):
        raise ValueError("Homography must be 3x3")
    u, v = point_px
    divisor = h[2][0] * u + h[2][1] * v + h[2][2]
    if not math.isfinite(divisor) or abs(divisor) < 1e-12:
        raise ValueError("Pixel projects to an invalid homogeneous coordinate")
    x = (h[0][0] * u + h[0][1] * v + h[0][2]) / divisor
    y = (h[1][0] * u + h[1][1] * v + h[1][2]) / divisor
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError("Non-finite projected point")
    return x, y


def apply_offset(offset: Pose2D, odom: Pose2D) -> Pose2D:
    """SE(2) 오프셋과 오도메트리로 지도 좌표계의 자세를 계산한다."""
    x0, y0, theta = offset
    xo, yo, yaw_o = odom
    c, s = math.cos(theta), math.sin(theta)
    return (x0 + xo * c - yo * s,
            y0 + xo * s + yo * c,
            wrap_angle(yaw_o + theta))


def fit_offset(offset: Pose2D, odom: Pose2D, camera: Pose2D, *,
               gain: float = 1.0,
               max_step_m: float = 0.1,
               max_step_rad: float = math.radians(10)) -> tuple[Pose2D, Pose2D]:
    """카메라 관측값을 향해 오프셋을 갱신하고 이동·회전 보정량을 제한한다."""
    if not 0 < gain <= 1 or max_step_m <= 0 or max_step_rad <= 0:
        raise ValueError("Invalid demonstration correction limits")
    mx, my, myaw = apply_offset(offset, odom)
    dx, dy = (camera[0] - mx) * gain, (camera[1] - my) * gain
    dyaw = wrap_angle(camera[2] - myaw) * gain
    distance = math.hypot(dx, dy)
    if distance > max_step_m:
        dx, dy = dx * max_step_m / distance, dy * max_step_m / distance
    dyaw = max(-max_step_rad, min(max_step_rad, dyaw))
    theta = wrap_angle(offset[2] + dyaw)
    c, s = math.cos(theta), math.sin(theta)
    x0 = mx + dx - (odom[0] * c - odom[1] * s)
    y0 = my + dy - (odom[0] * s + odom[1] * c)
    return (x0, y0, theta), (dx, dy, dyaw)


class OffsetCorrector:
    """정차 여부와 보정 지점, 관측 유효성을 확인해 오프셋을 갱신한다."""

    def __init__(self, offset: Pose2D = (0.0, 0.0, 0.0)) -> None:
        self.offset = offset

    def update(self, *, odom: Pose2D, camera: Pose2D,
               stationary: bool, at_correction_node: bool,
               fresh_observation: bool) -> Pose2D | None:
        """보정 조건이 충족되면 오프셋을 갱신하고 보정량을 반환한다."""
        if not (stationary and at_correction_node and fresh_observation):
            return None
        self.offset, delta = fit_offset(self.offset, odom, camera)
        return delta


if __name__ == "__main__":
    h = ((0.01, 0.0, 0.0), (0.0, 0.01, 0.0), (0.0, 0.0, 1.0))
    print("BEV point:", pixel_to_map(h, (100, 200)))
    corrector = OffsetCorrector()
    print("Stationary correction:", corrector.update(
        odom=(1.0, 0.0, 0.0), camera=(1.2, 0.0, 0.0),
        stationary=True, at_correction_node=True, fresh_observation=True))
