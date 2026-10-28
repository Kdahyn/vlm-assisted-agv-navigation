"""위험 감지, 이벤트 식별, 응답 검증과 운영자 승인 상태를 관리한다.
판단 결과는 stop_required=True인 Advisory로 반환한다."""
from __future__ import annotations

from dataclasses import dataclass
from secrets import token_hex

from src.vlm.schemas import SchemaError, validate_vlm_result


@dataclass(frozen=True)
class Advisory:
    status: str
    stop_required: bool = True
    request_id: str | None = None


class VLMSupervisor:
    """이벤트와 승인 상태를 바탕으로 대응 권고를 결정한다."""

    def __init__(self, *, approval_threshold: float = 0.7) -> None:
        if not 0 <= approval_threshold <= 1:
            raise ValueError("Approval threshold must be in [0, 1]")
        self.approval_threshold = approval_threshold  # 예제의 승인 요청 기준값.
        self.last_event_id: str | None = None
        self.pending: tuple[str, str] | None = None
        self.stop_required = True

    def on_hazard_detected(self, event_id: str) -> Advisory:
        """새 위험 이벤트를 등록하고 이전 승인 요청을 비운다."""
        if not event_id:
            raise ValueError("event_id required")
        self.last_event_id = event_id
        self.pending = None
        self.stop_required = True
        return Advisory("STOP_FIRST")

    def handle_event(self, event: dict, *, event_id: str) -> Advisory:
        """이벤트 식별자와 응답을 검증해 대응 권고를 반환한다."""
        if event_id != self.last_event_id:
            return Advisory("STALE_IGNORED")
        self.pending = None
        try:
            parsed = validate_vlm_result(event)
        except (SchemaError, ValueError, TypeError):
            return Advisory("INVALID_HOLD")
        action = parsed["motion_action"]
        confidence = parsed["confidence"]
        if action in {"HOLD_POSITION", "STOP_WAIT"}:
            return Advisory(action)
        if confidence < self.approval_threshold:
            request_id = token_hex(8)
            self.pending = (request_id, action)
            return Advisory("APPROVAL_REQUIRED", request_id=request_id)
        if action == "REROUTE_REQUEST":
            return Advisory("REPLAN_CANDIDATE")
        if action == "KEEP":
            return Advisory("RESUME_CANDIDATE")
        return Advisory("INVALID_HOLD")

    def on_operator_approval(self, *, request_id: str, approved: bool) -> Advisory:
        """대기 중인 요청과 승인 ID를 대조해 결과를 반환한다."""
        if self.pending is None or request_id != self.pending[0]:
            return Advisory("APPROVAL_IGNORED")
        _, action = self.pending
        self.pending = None
        if not approved:
            return Advisory("REJECTED_HOLD")
        return Advisory("REPLAN_CANDIDATE" if action == "REROUTE_REQUEST"
                        else "RESUME_CANDIDATE")


if __name__ == "__main__":
    supervisor = VLMSupervisor()
    print(supervisor.on_hazard_detected("demo-001"))
    print(supervisor.handle_event({"motion_action": "HOLD_POSITION"}, event_id="demo-001"))
