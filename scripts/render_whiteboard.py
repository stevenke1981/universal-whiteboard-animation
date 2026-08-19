#!/usr/bin/env python3
"""通用白板動畫單幕渲染器。

以 annotation 的語意順序、區域與時序，在持久畫布上先落墨再添彩。
預設不依賴固定手部圖片，使用程序化筆尖；也可傳入自訂透明 PNG。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from common import dump_json, ffmpeg_path, load_json


@dataclass
class RenderConfig:
    fps: int = 30
    cap_long_edge: int = 1080
    grid_edge: int = 10
    ink_path: str = "skeleton"
    color_fill: str = "wipe"
    pointer: str = "pen"
    pointer_image: Path | None = None
    pointer_height: int = 260
    pointer_anchor_x: float = 0.05
    pointer_anchor_y: float = 0.92
    background: str = "#F5EBD7"
    content_threshold: int = 30
    ink_threshold: int = 55
    ink_radius: int = 5
    brush_radius: int = 42
    ink_weight: int = 2
    color_weight: int = 1
    mask_policy_override: str | None = None
    finalize_mode: str = "union-only"
    final_fade_ms: int = 450
    keep_raw: bool = False


def imread_any(path: str | Path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    try:
        raw = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if raw.size == 0:
        return None
    return cv2.imdecode(raw, flags)


def hex_to_bgr(value: str) -> np.ndarray:
    digits = value.strip().lstrip("#")
    if len(digits) != 6:
        raise ValueError(f"非法色碼: {value}")
    red, green, blue = int(digits[:2], 16), int(digits[2:4], 16), int(digits[4:], 16)
    return np.array([blue, green, red], dtype=np.uint8)


def resize_aligned(image: np.ndarray, cap_long_edge: int) -> tuple[np.ndarray, float, float]:
    height, width = image.shape[:2]
    scale = 1.0
    if cap_long_edge > 0 and max(width, height) > cap_long_edge:
        scale = cap_long_edge / max(width, height)
    out_w = max(2, int(round(width * scale)))
    out_h = max(2, int(round(height * scale)))
    out_w -= out_w % 2
    out_h -= out_h % 2
    out_w = max(2, out_w)
    out_h = max(2, out_h)
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    resized = cv2.resize(image, (out_w, out_h), interpolation=interpolation)
    return resized, out_w / width, out_h / height


def sample_background(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    margin = max(3, min(height, width) // 45)
    patches = [
        image[:margin, :margin],
        image[:margin, width - margin :],
        image[height - margin :, :margin],
        image[height - margin :, width - margin :],
    ]
    pixels = np.concatenate([patch.reshape(-1, 3) for patch in patches], axis=0)
    return np.median(pixels, axis=0).astype(np.uint8)


def build_masks(image: np.ndarray, source_bg: np.ndarray, cfg: RenderConfig) -> tuple[np.ndarray, np.ndarray]:
    diff = np.abs(image.astype(np.int16) - source_bg.astype(np.int16)).sum(axis=2)
    content = diff >= cfg.content_threshold
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    bg_gray = float(cv2.cvtColor(source_bg.reshape(1, 1, 3), cv2.COLOR_BGR2GRAY)[0, 0])
    # 線條通常比紙張背景暗；同時保留非常深的彩色輪廓。
    ink = content & ((bg_gray - gray.astype(np.float32) >= cfg.ink_threshold) | (gray < 85))
    ink = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8)) > 0
    return content, ink


def scaled_rect(region: dict, sx: float, sy: float, width: int, height: int, padding: int = 0) -> tuple[int, int, int, int]:
    x0 = int(round(region["x"] * sx)) - padding
    y0 = int(round(region["y"] * sy)) - padding
    x1 = int(round((region["x"] + region["width"]) * sx)) + padding
    y1 = int(round((region["y"] + region["height"]) * sy)) + padding
    x0 = max(0, min(width, x0))
    x1 = max(0, min(width, x1))
    y0 = max(0, min(height, y0))
    y1 = max(0, min(height, y1))
    return x0, y0, x1, y1


def allowed_mask(
    element: dict,
    later_elements: list[dict],
    *,
    sx: float,
    sy: float,
    width: int,
    height: int,
    policy_override: str | None,
) -> np.ndarray:
    reveal = element.get("reveal") or {}
    padding = int(round(reveal.get("maskPaddingPx", 0) * (sx + sy) / 2))
    contour = ((element.get("handPath") or {}).get("contour")) or []
    if len(contour) >= 3:
        mask = rasterize_contour(contour, sx, sy, width, height)
        if padding > 0:
            kernel = np.ones((padding * 2 + 1, padding * 2 + 1), np.uint8)
            mask = cv2.dilate(mask.astype(np.uint8), kernel, iterations=1) > 0
    else:
        mask = np.zeros((height, width), dtype=bool)
        x0, y0, x1, y1 = scaled_rect(element["region"], sx, sy, width, height, padding=padding)
        mask[y0:y1, x0:x1] = True
    policy = policy_override or element.get("maskPolicy", "subtract-later")
    if policy == "subtract-later":
        for later in later_elements:
            later_contour = ((later.get("handPath") or {}).get("contour")) or []
            if len(later_contour) >= 3:
                mask &= ~rasterize_contour(later_contour, sx, sy, width, height)
            else:
                lx0, ly0, lx1, ly1 = scaled_rect(later["region"], sx, sy, width, height)
                mask[ly0:ly1, lx0:lx1] = False
    if policy in ("subtract-later", "explicit"):
        for protected in reveal.get("protectedRegions", []) or []:
            px0, py0, px1, py1 = scaled_rect(protected, sx, sy, width, height)
            mask[py0:py1, px0:px1] = False
    return mask


def rasterize_contour(
    contour: list,
    sx: float,
    sy: float,
    width: int,
    height: int,
) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    points = np.array([[int(round(float(x) * sx)), int(round(float(y) * sy))] for x, y in contour], dtype=np.int32)
    if len(points) >= 3:
        cv2.fillPoly(mask, [points], 1)
    return mask > 0


def scale_path_points(points: list, sx: float, sy: float) -> list[tuple[int, int]]:
    scaled: list[tuple[int, int]] = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        scaled.append((int(round(float(point[0]) * sx)), int(round(float(point[1]) * sy))))
    return scaled


def hand_path_from_element(element: dict, sx: float, sy: float) -> tuple[list[tuple[int, int]], set[int]] | None:
    payload = element.get("handPath") or {}
    raw_points = payload.get("points") or payload.get("contour") or []
    if len(raw_points) < 2:
        start, end = payload.get("start"), payload.get("end")
        if isinstance(start, (list, tuple)) and isinstance(end, (list, tuple)):
            raw_points = [start, end]
        else:
            return None
    points = scale_path_points(raw_points, sx, sy)
    if len(points) < 2:
        return None
    sampled = _resample_points(points, spacing=3.0)
    if len(sampled) < 2:
        sampled = [points[0], points[-1]]
    return sampled, set()


def _component_paths_from_grid(binary: np.ndarray, edge: int) -> list[list[tuple[int, int]]]:
    height, width = binary.shape
    ink_y, ink_x = np.nonzero(binary)
    if ink_y.size == 0:
        return []
    rows = math.ceil(height / edge)
    cols = math.ceil(width / edge)
    cells = np.zeros((rows, cols), dtype=np.uint8)
    cells[ink_y // edge, ink_x // edge] = 1
    count, labels = cv2.connectedComponents(cells, connectivity=8)
    paths: list[list[tuple[int, int]]] = []
    half = edge // 2
    for label in range(1, count):
        coords = np.argwhere(labels == label)
        if coords.size == 0:
            continue
        order = np.lexsort((coords[:, 1], coords[:, 0]))
        coords = coords[order]
        row_starts = np.flatnonzero(np.r_[True, coords[1:, 0] != coords[:-1, 0]])
        component: list[tuple[int, int]] = []
        reverse = False
        for start, end in zip(row_starts, np.r_[row_starts[1:], len(coords)]):
            block = coords[start:end]
            cols_present = block[::-1, 1] if reverse else block[:, 1]
            reverse = not reverse
            row = int(block[0, 0])
            y = min(height - 1, row * edge + half)
            for col in cols_present:
                x = min(width - 1, int(col) * edge + half)
                component.append((x, y))
        if component:
            paths.append(component)
    return paths


def morphological_skeleton(binary: np.ndarray) -> np.ndarray:
    source = (binary.astype(np.uint8) * 255).copy()
    skeleton = np.zeros_like(source)
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    max_iterations = max(source.shape) * 2
    for _ in range(max_iterations):
        opened = cv2.morphologyEx(source, cv2.MORPH_OPEN, element)
        residue = cv2.subtract(source, opened)
        skeleton = cv2.bitwise_or(skeleton, residue)
        source = cv2.erode(source, element)
        if cv2.countNonZero(source) == 0:
            break
    return skeleton


def _resample_points(points: Iterable[tuple[int, int]], spacing: float = 3.0) -> list[tuple[int, int]]:
    source = list(points)
    if len(source) < 2:
        return source
    result = [source[0]]
    carry = 0.0
    previous = np.array(source[0], dtype=float)
    for point in source[1:]:
        current = np.array(point, dtype=float)
        segment = current - previous
        length = float(np.linalg.norm(segment))
        if length <= 1e-6:
            continue
        direction = segment / length
        position = spacing - carry
        while position <= length:
            sample = previous + direction * position
            result.append((int(round(sample[0])), int(round(sample[1]))))
            position += spacing
        carry = max(0.0, length - (position - spacing))
        previous = current
    if result[-1] != source[-1]:
        result.append(source[-1])
    return result


def _component_paths_from_skeleton(binary: np.ndarray) -> list[list[tuple[int, int]]]:
    skeleton = morphological_skeleton(binary)
    contours, _ = cv2.findContours(skeleton, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    paths: list[list[tuple[int, int]]] = []
    for contour in contours:
        if len(contour) < 8:
            continue
        points = [(int(item[0][0]), int(item[0][1])) for item in contour]
        sampled = _resample_points(points, spacing=3.0)
        if len(sampled) >= 3:
            paths.append(sampled)
    return paths


def order_component_paths(paths: list[list[tuple[int, int]]]) -> list[list[tuple[int, int]]]:
    remaining = [path[:] for path in paths if path]
    ordered: list[list[tuple[int, int]]] = []
    cursor: tuple[int, int] | None = None
    while remaining:
        if cursor is None:
            index = min(range(len(remaining)), key=lambda i: (remaining[i][0][1], remaining[i][0][0]))
            path = remaining.pop(index)
        else:
            choices: list[tuple[float, int, bool]] = []
            for index, path_candidate in enumerate(remaining):
                d_start = math.dist(cursor, path_candidate[0])
                d_end = math.dist(cursor, path_candidate[-1])
                choices.append((min(d_start, d_end), index, d_end < d_start))
            _, index, reverse = min(choices, key=lambda item: item[0])
            path = remaining.pop(index)
            if reverse:
                path.reverse()
        ordered.append(path)
        cursor = path[-1]
    return ordered


def flatten_paths(paths: list[list[tuple[int, int]]]) -> tuple[list[tuple[int, int]], set[int]]:
    points: list[tuple[int, int]] = []
    pen_lifts: set[int] = set()
    for path in paths:
        if not path:
            continue
        if points:
            pen_lifts.add(len(points))
        points.extend(path)
    return points, pen_lifts


def build_stroke_path(ink_mask: np.ndarray, allowed: np.ndarray, cfg: RenderConfig) -> tuple[list[tuple[int, int]], set[int]]:
    binary = ink_mask & allowed
    if not binary.any():
        binary = allowed
    if cfg.ink_path == "skeleton":
        paths = _component_paths_from_skeleton(binary)
        if not paths:
            paths = _component_paths_from_grid(binary, cfg.grid_edge)
    else:
        paths = _component_paths_from_grid(binary, cfg.grid_edge)
    return flatten_paths(order_component_paths(paths))


def progress_indices(total_points: int, frames: int) -> list[int]:
    if total_points <= 0 or frames <= 0:
        return []
    if frames == 1:
        return [total_points - 1]
    return [round(index * (total_points - 1) / (frames - 1)) for index in range(frames)]


def ease(progress: float) -> float:
    progress = min(1.0, max(0.0, progress))
    return 0.5 - 0.5 * math.cos(math.pi * progress)


def load_pointer_image(path: Path | None, target_height: int) -> np.ndarray | None:
    if path is None:
        return None
    image = imread_any(path, cv2.IMREAD_UNCHANGED)
    if image is None or image.ndim != 3 or image.shape[2] not in (3, 4):
        raise ValueError(f"無法讀取指標圖片或缺少 alpha: {path}")
    if image.shape[2] == 3:
        alpha = np.full(image.shape[:2] + (1,), 255, dtype=np.uint8)
        image = np.concatenate([image, alpha], axis=2)
    scale = target_height / max(1, image.shape[0])
    width = max(1, int(round(image.shape[1] * scale)))
    return cv2.resize(image, (width, target_height), interpolation=cv2.INTER_AREA)


def overlay_rgba(frame: np.ndarray, overlay: np.ndarray, point: tuple[int, int], anchor_x: float, anchor_y: float) -> None:
    height, width = overlay.shape[:2]
    x0 = int(round(point[0] - anchor_x * width))
    y0 = int(round(point[1] - anchor_y * height))
    x1, y1 = x0 + width, y0 + height
    fx0, fy0 = max(0, x0), max(0, y0)
    fx1, fy1 = min(frame.shape[1], x1), min(frame.shape[0], y1)
    if fx1 <= fx0 or fy1 <= fy0:
        return
    ox0, oy0 = fx0 - x0, fy0 - y0
    ox1, oy1 = ox0 + (fx1 - fx0), oy0 + (fy1 - fy0)
    crop = overlay[oy0:oy1, ox0:ox1]
    alpha = crop[:, :, 3:4].astype(np.float32) / 255.0
    frame[fy0:fy1, fx0:fx1] = (
        frame[fy0:fy1, fx0:fx1].astype(np.float32) * (1.0 - alpha)
        + crop[:, :, :3].astype(np.float32) * alpha
    ).astype(np.uint8)


def draw_procedural_pointer(frame: np.ndarray, point: tuple[int, int], style: str) -> None:
    if style == "none":
        return
    x, y = int(point[0]), int(point[1])
    if style == "circle":
        cv2.circle(frame, (x, y), 13, (45, 45, 45), 3, lineType=cv2.LINE_AA)
        cv2.circle(frame, (x, y), 4, (40, 90, 220), -1, lineType=cv2.LINE_AA)
        return
    # 程序化筆：筆尖正好落在 point，筆桿向右下延伸。
    shaft_end = (x + 92, y + 76)
    cv2.line(frame, (x, y), shaft_end, (35, 35, 35), 15, lineType=cv2.LINE_AA)
    cv2.line(frame, (x + 8, y + 7), shaft_end, (210, 210, 205), 9, lineType=cv2.LINE_AA)
    cv2.circle(frame, (x, y), 5, (25, 25, 25), -1, lineType=cv2.LINE_AA)
    cv2.line(frame, (x + 55, y + 45), (x + 77, y + 63), (55, 115, 205), 7, lineType=cv2.LINE_AA)


class FrameWriter:
    def __init__(self, writer: cv2.VideoWriter, canvas: np.ndarray, cfg: RenderConfig, pointer_image: np.ndarray | None):
        self.writer = writer
        self.canvas = canvas
        self.cfg = cfg
        self.pointer_image = pointer_image
        self.frames_written = 0

    def write(self, pointer: tuple[int, int] | None = None) -> None:
        frame = self.canvas.copy()
        if pointer is not None:
            if self.pointer_image is not None:
                overlay_rgba(
                    frame,
                    self.pointer_image,
                    pointer,
                    self.cfg.pointer_anchor_x,
                    self.cfg.pointer_anchor_y,
                )
            else:
                draw_procedural_pointer(frame, pointer, self.cfg.pointer)
        self.writer.write(frame)
        self.frames_written += 1

    def hold_until(self, target_frame: int) -> None:
        while self.frames_written < target_frame:
            self.write(None)


def reveal_ink(
    fw: FrameWriter,
    source: np.ndarray,
    ink_mask: np.ndarray,
    allowed: np.ndarray,
    points: list[tuple[int, int]],
    pen_lifts: set[int],
    frames: int,
    cfg: RenderConfig,
) -> None:
    if frames <= 0:
        return
    if not points:
        for _ in range(frames):
            fw.write(None)
        return
    stroke = np.zeros(allowed.shape, dtype=np.uint8)
    targets = progress_indices(len(points), frames)
    last = -1
    for target in targets:
        if last < 0:
            cv2.circle(stroke, points[target], cfg.ink_radius, 255, -1, lineType=cv2.LINE_AA)
        else:
            for index in range(last + 1, target + 1):
                if index in pen_lifts:
                    cv2.circle(stroke, points[index], cfg.ink_radius, 255, -1, lineType=cv2.LINE_AA)
                    continue
                cv2.line(
                    stroke,
                    points[index - 1],
                    points[index],
                    255,
                    cfg.ink_radius * 2 + 1,
                    lineType=cv2.LINE_AA,
                )
        reveal = (stroke > 0) & ink_mask & allowed
        fw.canvas[reveal] = source[reveal]
        fw.write(points[target])
        last = target
    # 避免路徑稀疏造成線稿缺口。
    final_ink = ink_mask & allowed
    fw.canvas[final_ink] = source[final_ink]


def _wipe_mask(
    allowed: np.ndarray,
    direction: str,
    progress: float,
    rect: tuple[int, int, int, int],
) -> tuple[np.ndarray, tuple[int, int]]:
    x0, y0, x1, y1 = rect
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    p = ease(progress)
    canvas_h, canvas_w = allowed.shape
    mask = np.zeros((canvas_h, canvas_w), dtype=bool)
    if direction == "auto":
        direction = "left_to_right" if width >= height else "top_to_bottom"
    if direction == "right_to_left":
        boundary = x1 - int(round(width * p))
        mask[:, max(0, boundary) :] = True
        pointer = (max(x0, min(x1 - 1, boundary)), y0 + int((0.5 + 0.35 * math.sin(progress * 8 * math.pi)) * height))
    elif direction == "top_to_bottom":
        boundary = y0 + int(round(height * p))
        mask[: max(0, boundary + 1), :] = True
        pointer = (x0 + int((0.5 + 0.35 * math.sin(progress * 8 * math.pi)) * width), min(y1 - 1, boundary))
    elif direction == "bottom_to_top":
        boundary = y1 - int(round(height * p))
        mask[max(0, boundary) :, :] = True
        pointer = (x0 + int((0.5 + 0.35 * math.sin(progress * 8 * math.pi)) * width), max(y0, boundary))
    elif direction == "radial":
        center = (x0 + width / 2.0, y0 + height / 2.0)
        max_distance = math.hypot(width / 2.0, height / 2.0)
        radius = max_distance * p
        by0 = max(0, int(math.floor(center[1] - radius)))
        by1 = min(canvas_h, int(math.ceil(center[1] + radius)) + 1)
        bx0 = max(0, int(math.floor(center[0] - radius)))
        bx1 = min(canvas_w, int(math.ceil(center[0] + radius)) + 1)
        if by1 > by0 and bx1 > bx0:
            ys = np.arange(by0, by1, dtype=np.float32)[:, None]
            xs = np.arange(bx0, bx1, dtype=np.float32)[None, :]
            mask[by0:by1, bx0:bx1] = (xs - center[0]) ** 2 + (ys - center[1]) ** 2 <= radius * radius
        angle = progress * 5 * math.pi
        pointer = (
            int(center[0] + math.cos(angle) * radius),
            int(center[1] + math.sin(angle) * radius),
        )
    else:
        boundary = x0 + int(round(width * p))
        mask[:, : max(0, boundary + 1)] = True
        pointer = (min(x1 - 1, boundary), y0 + int((0.5 + 0.35 * math.sin(progress * 8 * math.pi)) * height))
    pointer = (max(0, min(allowed.shape[1] - 1, pointer[0])), max(0, min(allowed.shape[0] - 1, pointer[1])))
    return mask & allowed, pointer


def reveal_color_wipe(
    fw: FrameWriter,
    source: np.ndarray,
    content_mask: np.ndarray,
    allowed: np.ndarray,
    element: dict,
    frames: int,
    sx: float,
    sy: float,
) -> None:
    if frames <= 0:
        return
    rect = scaled_rect(element["region"], sx, sy, allowed.shape[1], allowed.shape[0])
    direction = (element.get("reveal") or {}).get("direction", "auto")
    for frame_index in range(frames):
        progress = 1.0 if frames == 1 else frame_index / (frames - 1)
        wave, pointer = _wipe_mask(allowed, direction, progress, rect)
        reveal = wave & content_mask
        fw.canvas[reveal] = source[reveal]
        fw.write(pointer)
    final = content_mask & allowed
    fw.canvas[final] = source[final]


def reveal_color_brush(
    fw: FrameWriter,
    source: np.ndarray,
    content_mask: np.ndarray,
    allowed: np.ndarray,
    points: list[tuple[int, int]],
    frames: int,
    cfg: RenderConfig,
) -> None:
    if frames <= 0:
        return
    if not points:
        paths = _component_paths_from_grid(content_mask & allowed, max(6, cfg.grid_edge * 2))
        points, _ = flatten_paths(order_component_paths(paths))
    if not points:
        for _ in range(frames):
            fw.write(None)
        return
    brush = np.zeros(allowed.shape, dtype=np.uint8)
    targets = progress_indices(len(points), frames)
    last = -1
    for target in targets:
        for index in range(max(0, last + 1), target + 1):
            cv2.circle(brush, points[index], cfg.brush_radius, 255, -1, lineType=cv2.LINE_AA)
        reveal = (brush > 0) & content_mask & allowed
        fw.canvas[reveal] = source[reveal]
        fw.write(points[target])
        last = target
    final = content_mask & allowed
    fw.canvas[final] = source[final]


def transcode_h264(raw_path: Path, output_path: Path, keep_raw: bool) -> tuple[Path, str]:
    ffmpeg = ffmpeg_path()
    if ffmpeg:
        command = [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(raw_path),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0 and output_path.exists():
            if not keep_raw:
                raw_path.unlink(missing_ok=True)
            return output_path, "h264"
        print(f"[warn] ffmpeg H.264 轉碼失敗，保留 mp4v: {result.stderr[-500:]}", file=sys.stderr)
    if raw_path != output_path:
        output_path.unlink(missing_ok=True)
        shutil.move(str(raw_path), str(output_path))
    return output_path, "mp4v"


def mux_audio(video_path: Path, audio_path: Path) -> tuple[Path, bool]:
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        print("[warn] 未找到 ffmpeg，無法加入音訊", file=sys.stderr)
        return video_path, False
    muxed = video_path.with_name(video_path.stem + ".audio.mp4")
    command = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(muxed),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[warn] 音訊合併失敗: {result.stderr[-500:]}", file=sys.stderr)
        muxed.unlink(missing_ok=True)
        return video_path, False
    video_path.unlink(missing_ok=True)
    muxed.replace(video_path)
    return video_path, True


def render(
    image_path: Path,
    annotation_path: Path,
    output_path: Path,
    cfg: RenderConfig,
    *,
    audio_path: Path | None = None,
    report_path: Path | None = None,
) -> dict:
    source_original = imread_any(image_path)
    if source_original is None:
        raise ValueError(f"無法讀取圖片: {image_path}")
    annotation = load_json(annotation_path)
    original_h, original_w = source_original.shape[:2]
    canvas = annotation.get("canvas") or {}
    if (canvas.get("width"), canvas.get("height")) != (original_w, original_h):
        raise ValueError(
            f"圖片尺寸 {original_w}x{original_h} 與 annotation canvas "
            f"{canvas.get('width')}x{canvas.get('height')} 不一致"
        )
    elements = sorted(annotation.get("elements") or [], key=lambda item: (item.get("sequence", 10**9), item.get("reveal", {}).get("startMs", 0)))
    if not elements:
        raise ValueError("annotation 沒有 elements")

    source, sx, sy = resize_aligned(source_original, cfg.cap_long_edge)
    out_h, out_w = source.shape[:2]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = output_path.with_name(output_path.stem + ".raw.mp4")
    raw_path.unlink(missing_ok=True)

    source_bg = sample_background(source)
    content_mask, ink_mask = build_masks(source, source_bg, cfg)
    background_value = annotation.get("background") or cfg.background
    background_bgr = hex_to_bgr(background_value)
    persistent = np.empty_like(source)
    persistent[...] = background_bgr

    pointer_image = load_pointer_image(cfg.pointer_image, cfg.pointer_height) if cfg.pointer_image else None
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(raw_path), fourcc, cfg.fps, (out_w, out_h))
    if not writer.isOpened():
        raise RuntimeError("無法開啟 OpenCV VideoWriter")
    fw = FrameWriter(writer, persistent, cfg, pointer_image)
    warnings: list[str] = []
    element_reports: list[dict] = []

    try:
        # 第一幀必須是乾淨畫布。
        fw.write(None)
        for index, element in enumerate(elements):
            reveal = element.get("reveal") or {}
            start_ms = int(reveal.get("startMs", 0))
            duration_ms = int(reveal.get("durationMs", 1))
            start_frame = max(1, round(start_ms * cfg.fps / 1000))
            if fw.frames_written < start_frame:
                fw.hold_until(start_frame)
            elif fw.frames_written > start_frame + 1:
                warnings.append(
                    f"{element.get('id')} 的 startMs 已落後目前筆畫；依 sequence 串行渲染。"
                )

            allowed = allowed_mask(
                element,
                elements[index + 1 :],
                sx=sx,
                sy=sy,
                width=out_w,
                height=out_h,
                policy_override=cfg.mask_policy_override,
            )
            allowed_pixels = int(allowed.sum())
            if allowed_pixels == 0:
                warnings.append(f"{element.get('id')} 的允許遮罩為空，已輸出靜止幀。")

            explicit = hand_path_from_element(element, sx, sy)
            if explicit:
                points, pen_lifts = explicit
            else:
                points, pen_lifts = build_stroke_path(ink_mask, allowed, cfg)
            total_frames = max(2, round(duration_ms * cfg.fps / 1000))
            weight_sum = max(1, cfg.ink_weight + cfg.color_weight)
            ink_frames = max(1, round(total_frames * cfg.ink_weight / weight_sum))
            color_frames = max(1, total_frames - ink_frames)
            reveal_ink(fw, source, ink_mask, allowed, points, pen_lifts, ink_frames, cfg)
            if cfg.color_fill == "brush":
                reveal_color_brush(fw, source, content_mask, allowed, points, color_frames, cfg)
            else:
                reveal_color_wipe(fw, source, content_mask, allowed, element, color_frames, sx, sy)

            element_reports.append(
                {
                    "id": element.get("id"),
                    "sequence": element.get("sequence"),
                    "allowedPixels": allowed_pixels,
                    "strokePoints": len(points),
                    "frames": total_frames,
                }
            )

        if cfg.finalize_mode == "fade-full":
            unassigned = content_mask & np.any(persistent != source, axis=2)
            fade_frames = max(1, round(cfg.final_fade_ms * cfg.fps / 1000))
            start_canvas = persistent.copy().astype(np.float32)
            for frame_index in range(fade_frames):
                alpha = (frame_index + 1) / fade_frames
                blended = start_canvas.copy()
                blended[unassigned] = (
                    start_canvas[unassigned] * (1.0 - alpha) + source[unassigned].astype(np.float32) * alpha
                )
                persistent[...] = blended.astype(np.uint8)
                fw.write(None)
        elif cfg.finalize_mode == "full-source":
            persistent[content_mask] = source[content_mask]

        scene_duration_ms = int(annotation.get("sceneDurationMs") or 0)
        final_hold_ms = int(annotation.get("finalHoldMs", 700))
        target_from_scene = round(scene_duration_ms * cfg.fps / 1000)
        target_with_hold = fw.frames_written + max(1, round(final_hold_ms * cfg.fps / 1000))
        target_frames = max(target_from_scene, target_with_hold)
        fw.hold_until(target_frames)
    finally:
        writer.release()

    final_path, codec = transcode_h264(raw_path, output_path, cfg.keep_raw)
    audio_added = False
    if audio_path is not None:
        final_path, audio_added = mux_audio(final_path, audio_path)

    report = {
        "valid": True,
        "image": str(image_path),
        "annotation": str(annotation_path),
        "output": str(final_path),
        "codec": codec,
        "audioAdded": audio_added,
        "size": {"width": out_w, "height": out_h},
        "fps": cfg.fps,
        "frames": fw.frames_written,
        "durationMs": round(fw.frames_written * 1000 / cfg.fps),
        "sourceBackgroundBgr": source_bg.tolist(),
        "canvasBackground": background_value,
        "elements": element_reports,
        "warnings": warnings,
    }
    if report_path:
        dump_json(report, report_path)
    return report


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="通用 SRT 白板動畫單幕渲染器")
    parser.add_argument("image")
    parser.add_argument("annotation")
    parser.add_argument("output")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--cap-long-edge", type=int, default=1080)
    parser.add_argument("--grid-edge", type=int, default=10)
    parser.add_argument("--ink-path", choices=["grid", "skeleton"], default="skeleton")
    parser.add_argument("--color-fill", choices=["wipe", "brush"], default="wipe")
    parser.add_argument("--pointer", choices=["pen", "circle", "none"], default="pen")
    parser.add_argument("--pointer-image", help="自訂透明 PNG；提供後優先於程序化 pointer")
    parser.add_argument("--pointer-height", type=int, default=260)
    parser.add_argument("--pointer-anchor-x", type=float, default=0.05)
    parser.add_argument("--pointer-anchor-y", type=float, default=0.92)
    parser.add_argument("--background", default="#F5EBD7")
    parser.add_argument("--content-threshold", type=int, default=30)
    parser.add_argument("--ink-threshold", type=int, default=55)
    parser.add_argument("--ink-radius", type=int, default=5)
    parser.add_argument("--brush-radius", type=int, default=42)
    parser.add_argument("--ink-weight", type=int, default=2)
    parser.add_argument("--color-weight", type=int, default=1)
    parser.add_argument("--mask-policy", choices=["subtract-later", "explicit", "none"])
    parser.add_argument("--finalize-mode", choices=["union-only", "fade-full", "full-source"], default="union-only")
    parser.add_argument("--final-fade-ms", type=int, default=450)
    parser.add_argument("--audio")
    parser.add_argument("--report")
    parser.add_argument("--keep-raw", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    cfg = RenderConfig(
        fps=max(1, args.fps),
        cap_long_edge=max(2, args.cap_long_edge),
        grid_edge=max(2, args.grid_edge),
        ink_path=args.ink_path,
        color_fill=args.color_fill,
        pointer=args.pointer,
        pointer_image=Path(args.pointer_image) if args.pointer_image else None,
        pointer_height=max(32, args.pointer_height),
        pointer_anchor_x=args.pointer_anchor_x,
        pointer_anchor_y=args.pointer_anchor_y,
        background=args.background,
        content_threshold=max(1, args.content_threshold),
        ink_threshold=max(1, args.ink_threshold),
        ink_radius=max(1, args.ink_radius),
        brush_radius=max(1, args.brush_radius),
        ink_weight=max(1, args.ink_weight),
        color_weight=max(1, args.color_weight),
        mask_policy_override=args.mask_policy,
        finalize_mode=args.finalize_mode,
        final_fade_ms=max(0, args.final_fade_ms),
        keep_raw=args.keep_raw,
    )
    try:
        report = render(
            Path(args.image),
            Path(args.annotation),
            Path(args.output),
            cfg,
            audio_path=Path(args.audio) if args.audio else None,
            report_path=Path(args.report) if args.report else None,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 2
    for warning in report["warnings"]:
        print(f"[warn] {warning}", file=sys.stderr)
    print(
        f"輸出 {report['size']['width']}x{report['size']['height']} @ {report['fps']}fps，"
        f"{report['durationMs']/1000:.2f}s，codec={report['codec']}"
    )
    print(f"OUTPUT={Path(report['output']).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
