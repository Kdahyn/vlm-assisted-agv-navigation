"""ROS 2 상태 토픽을 구독해 /navisight_public/demo_summary로 요약을 발행한다.
실행 환경: ROS 2 Humble, rclpy 및 메시지 패키지.
실행: python -m src.ros.topic_bridge"""
from __future__ import annotations

import json


ALLOWED_ACTIONS = {"KEEP", "STOP_WAIT", "REROUTE_REQUEST", "HOLD_POSITION"}


def launch_observer() -> None:
    """ROS 노드를 생성하고 구독·상태 요약 발행을 시작한다."""
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
    from nav_msgs.msg import Path
    from geometry_msgs.msg import PoseStamped

    class NAVISIGHTPublicObserver(Node):
        def __init__(self):
            super().__init__("navisight_public_observer")
            self.event_count = 0
            self.route_waypoints = 0
            self.pose_seen = False
            self.last_action = "NONE"
            self.follower_phase = "UNKNOWN"
            self.create_subscription(String, "/vlm_event", self.on_vlm_event, 10)
            self.create_subscription(String, "/follower_state", self.on_follower_state, 10)
            self.create_subscription(Path, "/route_path", self.on_path, 10)
            self.create_subscription(PoseStamped, "/overhead_pose", self.on_pose, 10)
            # 상태 요약을 전용 토픽으로 발행한다.
            self.demo_pub = self.create_publisher(
                String, "/navisight_public/demo_summary", 10)
            self.create_timer(1.0, self.publish_summary)

        def on_vlm_event(self, message):
            self.event_count += 1
            try:
                event = json.loads(message.data)
                action = event.get("final_action") or event.get("motion_action")
                self.last_action = action if action in ALLOWED_ACTIONS else "UNKNOWN"
            except (ValueError, TypeError, AttributeError):
                self.last_action = "INVALID"

        def on_follower_state(self, message):
            phase = message.data.split(" ", 1)[0]
            known = {"IDLE", "TURN", "GO", "WAIT", "FACE", "DONE", "ALIGN", "SETTLE", "SAFETY_STOP", "OPERATOR_HOLD"}
            self.follower_phase = phase if phase in known else "OTHER"

        def on_path(self, message):
            self.route_waypoints = len(message.poses)

        def on_pose(self, _message):
            self.pose_seen = True

        def publish_summary(self):
            # 이벤트 수와 주행 단계 등 지정된 상태만 요약한다.
            self.demo_pub.publish(String(data=json.dumps({
                "events_seen": self.event_count,
                "route_waypoints": self.route_waypoints,
                "overhead_pose_seen": self.pose_seen,
                "follower_phase": self.follower_phase,
                "last_action": self.last_action,
            })))

    rclpy.init()
    node = NAVISIGHTPublicObserver()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    launch_observer()
