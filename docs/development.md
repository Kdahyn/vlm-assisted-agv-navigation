# 코드와 로컬 실행

## 모듈 구성

| 영역 | 코드 | 입출력 및 구현 내용 |
| --- | --- | --- |
| 경로 계획 | [graph_planner.py](../src/navigation/graph_planner.py) · [example_map.json](../src/navigation/example_map.json) | 지도·차단 간선 → Dijkstra 경로·경유 경로 |
| 주행 상태 | [waypoint_controller.py](../src/navigation/waypoint_controller.py) | 계획 경로·도착 피드백 → `TURN / GO / FACE / WAIT` 상태 |
| 위치 보정 | [bev_localization.py](../src/navigation/bev_localization.py) | 호모그래피·오도메트리·카메라 자세 → 좌표 및 제한 보정량 |
| 감지 게이트 | [event_gate.py](../src/perception/event_gate.py) | 연속 검출·미검출 → 활성 감지 신호 |
| 트리거·프레임 | [hazard_pipeline.py](../src/perception/hazard_pipeline.py) | 감지·시간순 프레임 경로 → `HazardTrigger` |
| 이미지 정렬 | [frame_manager.py](../src/vlm/frame_manager.py) | 이미지 폴더 → 자연 정렬·표본 프레임 |
| Bedrock 호출 | [bedrock_example.py](../src/vlm/bedrock_example.py) | 이미지 → Converse 요청·장면 설명 텍스트 |
| 응답 검증 | [schemas.py](../src/vlm/schemas.py) | VLM 응답 → 필드·열거값·신뢰도 검증 |
| 판단 상태 | [safety_supervisor.py](../src/vlm/safety_supervisor.py) | 이벤트·응답·승인 ID → `Advisory` |
| ROS 2 상태 | [topic_bridge.py](../src/ros/topic_bridge.py) | 시스템 상태 구독 → 요약 토픽 발행 |
| 테스트 | [test_public_examples.py](../tests/test_public_examples.py) | 모듈 검증·모의 파이프라인 연결 |

주행 모듈은 상태 전이를 반환하고 안전 감독 모듈은 정지 권고를 포함한 `Advisory`를 반환합니다. ROS 2 예제는 관측한 상태를 `/navisight_public/demo_summary`로 발행합니다.

## 실행 환경

Python 3.10 이상에서 저장소 루트를 기준으로 실행합니다. 이미지 입출력 테스트에는 Pillow가 필요합니다.

```bash
python -m pip install pillow
python -m unittest discover -s tests -v
```

테스트는 경로 차단과 대체 경로, 웨이포인트 상태 전이, BEV 보정, 프레임 선택, 응답 형식, 운영자 승인 ID, 모의 Bedrock 응답을 확인합니다.

## 개별 예제

```bash
python src/navigation/graph_planner.py
python -m src.navigation.waypoint_controller
python -m src.navigation.bev_localization
python -m src.perception.hazard_pipeline
python research/experiments/threshold_analysis.py
```

## ROS 2 상태 관측

ROS 2 Humble과 `rclpy`, `std_msgs`, `nav_msgs`, `geometry_msgs`가 설치된 환경에서 실행합니다.

```bash
python -m src.ros.topic_bridge
```

`/vlm_event`, `/follower_state`, `/route_path`, `/overhead_pose`를 구독하고 이벤트 수·경유점 수·주행 단계 등 요약 정보를 발행합니다.

[ROS 2 인터페이스](architecture.md) · [Bedrock API 실행](bedrock_api.md) · [메인 README](../README.md)
