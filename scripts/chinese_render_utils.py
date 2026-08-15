#!/usr/bin/env python3
"""中文字逐筆渲染器的 mask、median、筆尖與 frame 工具。"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from render_whiteboard_base import imread_any, progress_indices

@dataclass
class ChineseRenderConfig:
    fps: int = 30
    cap_long_edge: int = 1080
    pointer: str = "pen"
    ink_radius: int = 5
    background: str = "#F5EBD7"
    keep_raw: bool = False
    finalize_mode: str = "union-only"

def _corner_median(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    m = max(1, min(h, w) // 40)
    parts = [image[:m, :m], image[:m, w-m:], image[h-m:, :m], image[h-m:, w-m:]]
    pixels = np.concatenate([part.reshape(-1, part.shape[2]) for part in parts])
    return np.median(pixels, axis=0)

def _mask_from_image(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return np.abs(image.astype(np.float32) - float(np.median(image))) >= 8
    if image.ndim == 3 and image.shape[2] == 4:
        alpha = image[:, :, 3]
        if int(alpha.min()) < 250:
            return alpha >= 8
        image = image[:, :, :3]
    if image.ndim != 3:
        raise ValueError(f"不支援的 mask 維度: {image.shape}")
    bg = _corner_median(image).astype(np.float32).reshape(1, 1, -1)
    return np.abs(image[:, :, :3].astype(np.float32) - bg).sum(axis=2) >= 18

def load_element_mask(element: dict, annotation_path: Path, width: int, height: int) -> tuple[np.ndarray, Path]:
    reveal = element.get("reveal") or {}
    raw = element.get("strokeMask") or reveal.get("maskPath")
    if not raw:
        raise ValueError(f"{element.get('id')} 缺少 strokeMask")
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = (annotation_path.parent / path).resolve()
    image = imread_any(path, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"無法讀取 strokeMask: {path}")
    mask = _mask_from_image(image)
    if mask.shape != (height, width):
        mask = cv2.resize(mask.astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST) > 0
    if not mask.any():
        raise ValueError(f"strokeMask 沒有有效像素: {path}")
    return mask, path

def _resample(points: list[tuple[int, int]], spacing: float = 2.0) -> list[tuple[int, int]]:
    if len(points) < 2:
        return points
    result = [points[0]]
    carry = 0.0
    previous = np.asarray(points[0], dtype=float)
    for raw in points[1:]:
        current = np.asarray(raw, dtype=float)
        segment = current - previous
        length = float(np.linalg.norm(segment))
        if length <= 1e-6:
            continue
        direction = segment / length
        position = spacing - carry
        while position <= length:
            sample = previous + direction * position
            point = (int(round(sample[0])), int(round(sample[1])))
            if point != result[-1]:
                result.append(point)
            position += spacing
        carry = max(0.0, length - (position - spacing))
        previous = current
    if result[-1] != points[-1]:
        result.append(points[-1])
    return result

def hand_path_points(element: dict, sx: float, sy: float, width: int, height: int) -> list[tuple[int, int]]:
    hand = element.get("handPath") or {}
    raw_points = hand.get("points")
    if not isinstance(raw_points, list) or len(raw_points) < 2:
        raise ValueError(f"{element.get('id')} 缺少 median handPath.points")
    points: list[tuple[int, int]] = []
    for raw in raw_points:
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            raise ValueError(f"{element.get('id')} handPath.points 格式錯誤")
        x = max(0, min(width - 1, int(round(float(raw[0]) * sx))))
        y = max(0, min(height - 1, int(round(float(raw[1]) * sy))))
        if not points or points[-1] != (x, y):
            points.append((x, y))
    if len(points) < 2:
        raise ValueError(f"{element.get('id')} median 至少需要兩點")
    return _resample(points)

def _pointer(frame: np.ndarray, point: tuple[int, int], style: str) -> None:
    if style == "none":
        return
    x, y = point
    if style == "circle":
        cv2.circle(frame, (x, y), 10, (35, 35, 35), 2, cv2.LINE_AA)
        return
    # 程序化筆：筆尖正好落在 point，避免依賴固定 PNG。
    cv2.line(frame, (x + 7, y - 7), (x + 80, y - 80), (48, 48, 48), 13, cv2.LINE_AA)
    cv2.line(frame, (x + 7, y - 7), (x + 80, y - 80), (230, 214, 179), 8, cv2.LINE_AA)
    cv2.circle(frame, (x, y), 4, (25, 25, 25), -1, cv2.LINE_AA)

class ChineseFrameWriter:
    def __init__(self, writer: cv2.VideoWriter, canvas: np.ndarray):
        self.writer = writer
        self.canvas = canvas
        self.frames_written = 0

    def write(self, pointer_style: str = "none", point: tuple[int, int] | None = None) -> None:
        frame = self.canvas.copy()
        if point is not None:
            _pointer(frame, point, pointer_style)
        self.writer.write(frame)
        self.frames_written += 1

    def hold_until(self, target_frame: int) -> None:
        while self.frames_written < target_frame:
            self.write()

def _write_stroke(
    fw: ChineseFrameWriter,
    canvas: np.ndarray,
    source: np.ndarray,
    mask: np.ndarray,
    points: list[tuple[int, int]],
    frames: int,
    radius: int,
    pointer_style: str,
) -> None:
    trace = np.zeros(mask.shape, dtype=np.uint8)
    indices = progress_indices(len(points), max(1, frames))
    last = -1
    for target in indices:
        if last < 0:
            cv2.circle(trace, points[target], radius, 255, -1, cv2.LINE_AA)
        else:
            for idx in range(last + 1, target + 1):
                cv2.line(trace, points[idx - 1], points[idx], 255, radius * 2 + 1, cv2.LINE_AA)
        visible = (trace > 0) & mask
        canvas[visible] = source[visible]
        fw.write(pointer_style, points[target])
        last = target
    canvas[mask] = source[mask]
