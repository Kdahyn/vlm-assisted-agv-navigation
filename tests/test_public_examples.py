"""경로 계획·상태 전이·VLM 입출력을 하드웨어 없이 검증한다.
실행: python -m unittest discover -s tests -v"""
import math
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from src.navigation.bev_localization import (
    OffsetCorrector, apply_offset, fit_offset, pixel_to_map,
)
from src.navigation.graph_planner import RouteGraph
from src.navigation.waypoint_controller import Feedback, Phase, WaypointFollower
from src.perception.event_gate import Gate
from src.perception.hazard_pipeline import VLMTriggerBridge
from src.vlm.bedrock_example import make_content, describe_frames, BedrockExampleError
from src.vlm.safety_supervisor import VLMSupervisor
from src.vlm.schemas import SchemaError, validate_vlm_result


VALID_EVENT = {
    "scene_type": "working",
    "occupancy_type": "long_term",
    "temporal_trend": "stable",
    "risk_level": "medium",
    "motion_action": "REROUTE_REQUEST",
    "operator_action": "NOTIFY",
    "confidence": 0.92,
    "route_restriction": True,
    "reason": "Fictional work zone on example edge",
}


class TestRouteGraph(unittest.TestCase):
    def test_blocked_edge_yields_alternative(self):
        file = Path(__file__).resolve().parents[1] / "src/navigation/example_map.json"
        graph = RouteGraph(file)
        original = graph.plan("START", "GOAL")
        self.assertIsNotNone(original)
        graph.block_edge("B", "GOAL")
        revised = graph.plan("START", "GOAL")
        self.assertIsNotNone(revised)
        self.assertNotEqual(original, revised)
        self.assertNotIn({"B", "GOAL"}, (set(p) for p in zip(revised, revised[1:])))

    def test_blocked_nonexistent_edge_rejected(self):
        file = Path(__file__).resolve().parents[1] / "src/navigation/example_map.json"
        graph = RouteGraph(file)
        with self.assertRaises(ValueError):
            graph.block_edge("START", "GOAL")


class TestWaypointState(unittest.TestCase):
    def test_independent_safety_stop_freezes_progress(self):
        follower = WaypointFollower()
        follower.on_path(["START", "A", "GOAL"], {1})
        self.assertEqual(follower.control(Feedback(heading_aligned=True)), "GO")
        follower.on_safety_stop(True)
        self.assertEqual(follower.control(Feedback(waypoint_reached=True)), "SAFETY_STOP")
        self.assertEqual(follower.phase, Phase.GO)
        self.assertEqual(follower.index, 1)
        follower.on_operator_hold(True)
        self.assertEqual(follower.control(Feedback(waypoint_reached=True)), "OPERATOR_HOLD")
        follower.on_safety_stop(False)
        self.assertEqual(follower.control(Feedback(waypoint_reached=True)), "OPERATOR_HOLD")
        follower.on_operator_hold(False)
        self.assertEqual(follower.control(Feedback(waypoint_reached=True)), "FACE")
        self.assertEqual(follower.control(Feedback(final_heading_aligned=True)), "WAIT")
        self.assertEqual(follower.control(Feedback(dwell_complete=True)), "TURN")

    def test_invalid_stops_leave_existing_path_unchanged(self):
        follower = WaypointFollower()
        follower.on_path(["START", "A", "GOAL"], {1})
        before = (follower.path, follower.index, follower.stops.copy(), follower.phase)
        with self.assertRaises(ValueError):
            follower.on_path(["X", "Y"], {99})
        self.assertEqual((follower.path, follower.index, follower.stops, follower.phase), before)
        with self.assertRaises(ValueError):
            follower.on_path(["X", "Y"], {"1"})
        self.assertEqual((follower.path, follower.index, follower.stops, follower.phase), before)

    def test_arrival(self):
        follower = WaypointFollower()
        follower.on_path(["START", "GOAL"])
        for fb in [Feedback(heading_aligned=True), Feedback(waypoint_reached=True),
                   Feedback(final_heading_aligned=True)]:
            follower.control(fb)
        self.assertEqual(follower.phase, Phase.DONE)


class TestBEVLocalization(unittest.TestCase):
    def test_homography_project(self):
        h = ((0.02, 0, 0), (0, 0.02, 0), (0, 0, 1))
        self.assertEqual(pixel_to_map(h, (100, 50)), (2.0, 1.0))
        with self.assertRaises(ValueError):
            pixel_to_map(((1, 0, 0), (0, 1, 0), (0, 0, 0)), (1, 1))

    def test_fit_offset_bounded_and_stationary_gated(self):
        old = (0.0, 0.0, 0.0)
        odom = (1.0, 0.0, 0.0)
        camera = (1.8, 0.3, math.radians(20))
        new, step = fit_offset(old, odom, camera, max_step_m=0.10,
                               max_step_rad=math.radians(5))
        self.assertLessEqual(math.hypot(step[0], step[1]), 0.1000001)
        self.assertLessEqual(abs(step[2]), math.radians(5) + 1e-8)
        self.assertAlmostEqual(apply_offset(new, odom)[0], 1.0 + step[0])
        corrector = OffsetCorrector()
        self.assertIsNone(corrector.update(
            odom=odom, camera=camera, stationary=False,
            at_correction_node=True, fresh_observation=True))
        self.assertEqual(corrector.offset, old)
        self.assertIsNotNone(corrector.update(
            odom=odom, camera=camera, stationary=True,
            at_correction_node=True, fresh_observation=True))


class TestTriggerAndSupervisor(unittest.TestCase):
    def test_debounce(self):
        gate = Gate(hits=2, misses=2)
        self.assertFalse(gate.update(True))
        self.assertTrue(gate.update(True))
        self.assertFalse(gate.update(False))
        self.assertFalse(gate.update(False))
        self.assertFalse(gate.active)

    def test_frame_window_one_event(self):
        bridge = VLMTriggerBridge(max_frames=4, window_seconds=2)
        for i in range(8):
            bridge.image_callback(i * 0.5, f"fictional_{i}.jpg")
        self.assertIsNone(bridge.trigger_callback(detected=True, category="PERSON", now=3.5))
        event = bridge.trigger_callback(detected=True, category="PERSON", now=3.5)
        self.assertTrue(event.stop_required)
        self.assertEqual(len(event.frames), 4)
        self.assertEqual(event.frames[-1].name, "fictional_7.jpg")
        self.assertIsNone(bridge.trigger_callback(detected=True, category="PERSON", now=3.5))

    def test_no_frame_stops_without_vlm_request_then_recovers(self):
        bridge = VLMTriggerBridge()
        self.assertIsNone(bridge.trigger_callback(detected=True, category="PERSON", now=0.0))
        event = bridge.trigger_callback(detected=True, category="PERSON", now=0.0)
        self.assertTrue(event.stop_required)
        self.assertFalse(event.vlm_ready)
        bridge.image_callback(0.1, "fictional_frame.jpg")
        later = bridge.trigger_callback(detected=True, category="PERSON", now=0.1)
        self.assertTrue(later.vlm_ready)
        self.assertEqual(len(later.frames), 1)

    def test_stop_before_assessment_and_reject_stale(self):
        supervisor = VLMSupervisor(approval_threshold=0.70)
        self.assertEqual(supervisor.on_hazard_detected("e1").status, "STOP_FIRST")
        self.assertTrue(supervisor.stop_required)
        self.assertEqual(supervisor.handle_event(VALID_EVENT, event_id="e0").status, "STALE_IGNORED")
        self.assertEqual(supervisor.handle_event(VALID_EVENT, event_id="e1").status, "REPLAN_CANDIDATE")
        self.assertTrue(supervisor.stop_required)  # 응답 처리 후에도 정지 권고를 유지한다.

    def test_low_confidence_correlated_operator_approval(self):
        supervisor = VLMSupervisor(approval_threshold=0.70)
        supervisor.on_hazard_detected("e1")
        low = dict(VALID_EVENT, confidence=0.40)
        result = supervisor.handle_event(low, event_id="e1")
        self.assertEqual(result.status, "APPROVAL_REQUIRED")
        self.assertEqual(supervisor.on_operator_approval(
            request_id="wrong", approved=True).status, "APPROVAL_IGNORED")
        self.assertEqual(supervisor.on_operator_approval(
            request_id=result.request_id, approved=True).status, "REPLAN_CANDIDATE")
        self.assertTrue(supervisor.stop_required)

    def test_invalid_output_holds(self):
        supervisor = VLMSupervisor()
        supervisor.on_hazard_detected("e1")
        self.assertEqual(supervisor.handle_event(
            dict(VALID_EVENT, confidence="high"), event_id="e1").status, "INVALID_HOLD")
        with self.assertRaises(SchemaError):
            validate_vlm_result(dict(VALID_EVENT, route_restriction="false"))

    def test_mock_event_to_replanned_graph(self):
        """모의 감지 이벤트에서 정지 권고와 대체 경로 계산까지 검증한다."""
        bridge = VLMTriggerBridge()
        for i in range(4):
            bridge.image_callback(i * 0.5, f"fictional_{i}.jpg")
        bridge.trigger_callback(detected=True, category="WORK_ZONE", now=1.5)
        trigger = bridge.trigger_callback(detected=True, category="WORK_ZONE", now=1.5)
        self.assertTrue(trigger.stop_required)
        follower = WaypointFollower()
        follower.on_path(["START", "A", "GOAL"])
        follower.on_safety_stop(True)
        self.assertEqual(follower.control(Feedback(heading_aligned=True)), "SAFETY_STOP")
        supervisor = VLMSupervisor()
        supervisor.on_hazard_detected("demo-event")
        result = supervisor.handle_event(VALID_EVENT, event_id="demo-event")
        self.assertEqual(result.status, "REPLAN_CANDIDATE")
        graph = RouteGraph(Path(__file__).resolve().parents[1]
                           / "src/navigation/example_map.json")
        first = graph.plan("START", "GOAL")
        # 테스트 지도에서 장애물에 해당하는 간선을 지정한다.
        graph.block_edge("B", "GOAL")
        alternate = graph.plan("START", "GOAL")
        self.assertNotEqual(first, alternate)
        self.assertTrue(supervisor.stop_required)
        self.assertTrue(follower.safety_stop)


class FakeBedrockRuntime:
    def converse(self, **kwargs):
        assert kwargs["modelId"] == "fake-model"
        assert kwargs["messages"][0]["content"][-1]["image"]["format"] == "jpeg"
        return {"stopReason": "end_turn", "output": {"message": {"content": [
            {"text": "Fictional frame received. No motion authorization."}]}}}


class TestBedrockMock(unittest.TestCase):
    def test_image_blocks_and_mock_cloud(self):
        with tempfile.TemporaryDirectory() as folder:
            example = Path(folder) / "frame.jpg"
            Image.new("RGB", (16, 12), (120, 130, 140)).save(example, format="JPEG")
            content = make_content([example])
            self.assertEqual(len(content), 3)
            result = describe_frames([example], model_id="fake-model",
                                     region="us-east-1", runtime=FakeBedrockRuntime())
            self.assertIn("No motion authorization", result)

    def test_reject_fake_image_and_accept_webp_as_jpeg(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = Path(folder) / "fake.jpg"
            fake.write_bytes(b"not an actual jpeg")
            with self.assertRaises(BedrockExampleError):
                make_content([fake])
            webp = Path(folder) / "frame.webp"
            Image.new("RGB", (24, 16), "white").save(webp, format="WEBP")
            result = make_content([webp])
            self.assertEqual(result[-1]["image"]["format"], "jpeg")
            self.assertTrue(result[-1]["image"]["source"]["bytes"].startswith(b"\xff\xd8"))


if __name__ == "__main__":
    unittest.main()
