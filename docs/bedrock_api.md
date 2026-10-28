# Bedrock 이미지 요청 예제

시간순 이미지로 Amazon Bedrock Converse 요청을 구성하고 장면 설명 텍스트를 받는 예제입니다.

[bedrock_example.py](../src/vlm/bedrock_example.py)

## 입력 처리

1. JPEG·PNG·WebP 파일 1~4장을 오래된 프레임부터 전달합니다.
2. 이미지를 디코딩해 검증하고 EXIF 방향을 반영합니다.
3. RGB JPEG로 변환해 시간순 이미지 블록을 구성합니다.
4. 응답 종료 상태와 텍스트 블록을 확인합니다.

## 로컬 입력 검사

```bash
python -m pip install boto3 pillow
python src/vlm/bedrock_example.py assets/port_testbed.jpg
```

기본 실행은 이미지 입력과 요청 블록을 로컬에서 확인합니다.

## API 호출

AWS 인증은 환경변수, AWS CLI 프로필 또는 IAM Role로 설정합니다. `--invoke`를 지정하면 이미지를 AWS로 전송하고 호출 비용이 발생합니다.

```bash
export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID=qwen.qwen3-vl-235b-a22b
python src/vlm/bedrock_example.py --invoke /path/to/frame.jpg
```

모델과 리전은 `--model-id`, `--region`으로도 지정할 수 있습니다.

## 응답 처리

`make_content()`가 이미지 블록을 만들고 `describe_frames()`가 장면 설명 문자열을 반환합니다. 판단 필드 검증은 [schemas.py](../src/vlm/schemas.py), 이벤트와 승인 상태 관리는 [safety_supervisor.py](../src/vlm/safety_supervisor.py)에서 확인할 수 있습니다.

[코드와 실행](development.md) · [메인 README](../README.md)
