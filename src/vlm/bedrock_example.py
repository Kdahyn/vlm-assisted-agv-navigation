"""시간순 이미지로 Amazon Bedrock Converse 요청을 구성하고 장면 설명을 반환한다.
기본 실행은 로컬 이미지 검사다. --invoke는 이미지를 AWS로 전송하며 호출 비용이 발생한다."""
from __future__ import annotations

import argparse
import io
import os
from pathlib import Path


PUBLIC_SYSTEM_PROMPT = (
    "Describe the visually observable scene. Distinguish observations from "
    "uncertainties. Do not issue robot motion commands or safety clearances."
)
PUBLIC_USER_PROMPT = "Summarize visible objects and possible ambiguities across the frames."
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_BYTES = 3_750_000


class BedrockExampleError(RuntimeError):
    """이미지 입력 검증 또는 Bedrock 요청 처리 오류."""


def make_content(frames: list[Path]) -> list[dict]:
    """시간순 RGB 이미지를 검증해 Converse 이미지 블록으로 구성한다."""
    if not 1 <= len(frames) <= 4:
        raise BedrockExampleError("Provide 1 to 4 chronological image files")
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise BedrockExampleError("Install Pillow to decode and validate image files") from exc
    content = [{"text": PUBLIC_USER_PROMPT}]
    for i, raw in enumerate(frames, start=1):
        path = Path(raw)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise BedrockExampleError(f"Unsupported image extension: {path.suffix}")
        try:
            with Image.open(path) as image:
                image.load()  # 파일을 디코딩해 이미지 유효성을 검사한다.
                rgb = ImageOps.exif_transpose(image).convert("RGB")
                rgb.thumbnail((1280, 1280))  # 요청 이미지의 최대 크기.
                buffer = io.BytesIO()
                rgb.save(buffer, format="JPEG", quality=85)
                image_bytes = buffer.getvalue()
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise BedrockExampleError(f"Cannot decode image: {path.name}") from exc
        if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
            raise BedrockExampleError(f"Invalid encoded image size: {path.name}")
        content.extend([
            {"text": f"Chronological frame {i} of {len(frames)}"},
            {"image": {"format": "jpeg", "source": {"bytes": image_bytes}}},
        ])
    return content


def describe_frames(frames: list[Path], *, model_id: str, region: str,
                    runtime=None) -> str:
    """프레임을 Bedrock에 전달하고 장면 설명 텍스트를 반환한다.
    클라이언트를 주입하지 않으면 boto3의 기본 인증 체인을 사용한다."""
    if not model_id:
        raise BedrockExampleError("Set BEDROCK_MODEL_ID before invoking AWS")
    content = make_content(frames)
    if runtime is None:
        try:
            import boto3
            from botocore.config import Config
            runtime = boto3.client(
                "bedrock-runtime",
                region_name=region,
                config=Config(connect_timeout=10, read_timeout=60,
                              retries={"mode": "standard", "total_max_attempts": 2}),
            )
        except Exception as exc:
            raise BedrockExampleError(
                "Unable to initialize Bedrock client; check boto3 and IAM setup"
            ) from exc
    try:
        result = runtime.converse(
            modelId=model_id,
            system=[{"text": PUBLIC_SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": content}],
            inferenceConfig={"maxTokens": 512, "temperature": 0.0},
        )
    except Exception as exc:
        # 오류 코드만 기록해 요청 본문과 인증정보의 노출을 막는다.
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", type(exc).__name__)
        raise BedrockExampleError(f"Bedrock invocation failed ({code})") from exc
    if result.get("stopReason") not in ("end_turn", "stop_sequence"):
        raise BedrockExampleError("Incomplete or rejected VLM response")
    blocks = result.get("output", {}).get("message", {}).get("content", [])
    text = "\n".join(b["text"] for b in blocks if isinstance(b, dict)
                     and isinstance(b.get("text"), str))
    if not text.strip():
        raise BedrockExampleError("Model returned no text")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames", nargs="+", type=Path,
                        help="1-4 pre-reviewed local JPEG/PNG/WebP images, oldest first")
    parser.add_argument("--invoke", action="store_true",
                        help="Actually contact Bedrock (AWS credentials and charges apply)")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--model-id", default=os.getenv("BEDROCK_MODEL_ID", ""))
    args = parser.parse_args()
    if not args.invoke:
        content = make_content(args.frames)
        print(f"Dry run: {len(args.frames)} frames, {len(content)} Converse content blocks")
        print("No AWS request was sent. Add --invoke explicitly to call Bedrock.")
        return
    print(describe_frames(args.frames, model_id=args.model_id, region=args.region))


if __name__ == "__main__":
    try:
        main()
    except BedrockExampleError as exc:
        raise SystemExit(str(exc)) from None
