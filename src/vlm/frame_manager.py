"""이미지 파일을 자연 정렬하고 처음·마지막 프레임을 포함해 표본을 선택한다."""
from __future__ import annotations
import re
from pathlib import Path

SUPPORTED = {'.jpg', '.jpeg', '.png', '.webp'}


def _natural_key(path: Path):
    return [(1, int(p)) if p.isdigit() else (0, p)
            for p in re.split(r'(\d+)', path.name.lower())]


def sample_paths(paths: list[Path], max_frames: int) -> list[Path]:
    if max_frames < 2:
        raise ValueError('max_frames must be at least 2')
    if len(paths) <= max_frames:
        return list(paths)
    # 처음과 마지막 프레임을 포함한다.
    return [paths[round(i * (len(paths) - 1) / (max_frames - 1))]
            for i in range(max_frames)]


def collect_image_paths(input_dir: str | Path, max_frames: int | None = None) -> list[Path]:
    folder = Path(input_dir)
    if not folder.is_dir():
        raise FileNotFoundError(f'Image directory does not exist: {folder}')
    paths = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED),
                   key=_natural_key)
    if not paths:
        raise FileNotFoundError(f'No original images found in {folder}')
    return sample_paths(paths, max_frames) if max_frames is not None else paths
