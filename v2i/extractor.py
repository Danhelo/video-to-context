"""Frame extraction from videos and GIFs."""

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image


@dataclass
class MediaInfo:
    """Information about a media file."""

    path: str
    width: int
    height: int
    duration: float  # seconds
    frame_count: int
    fps: float
    format: str  # 'video', 'gif', 'image'
    codec: Optional[str] = None

    @property
    def is_animated(self) -> bool:
        return self.frame_count > 1

    def __str__(self) -> str:
        if self.format == "gif":
            return f"GIF {self.width}x{self.height}, {self.frame_count} frames, {self.duration:.1f}s"
        elif self.format == "video":
            return f"Video {self.width}x{self.height}, {self.duration:.1f}s, {self.fps:.1f}fps"
        else:
            return f"Image {self.width}x{self.height}"


def check_ffmpeg() -> bool:
    """Check if ffmpeg is available."""
    return shutil.which("ffmpeg") is not None


def check_ffprobe() -> bool:
    """Check if ffprobe is available."""
    return shutil.which("ffprobe") is not None


def _run_ffprobe(path: str) -> Optional[dict]:
    """Run ffprobe and return JSON output."""
    if not check_ffprobe():
        return None

    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return None


def get_media_info(path: str) -> Optional[MediaInfo]:
    """
    Get information about a media file.

    Works with videos, GIFs, and images.
    """
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return None

    # Try PIL first for GIFs and images
    try:
        with Image.open(path) as img:
            width, height = img.size
            fmt = img.format.lower() if img.format else "unknown"

            if fmt == "gif":
                # Count GIF frames
                frame_count = 0
                total_duration = 0
                try:
                    while True:
                        frame_count += 1
                        # Get frame duration (in milliseconds)
                        duration = img.info.get("duration", 100)
                        total_duration += duration
                        img.seek(img.tell() + 1)
                except EOFError:
                    pass

                duration_sec = total_duration / 1000.0
                fps = frame_count / duration_sec if duration_sec > 0 else 10.0

                return MediaInfo(
                    path=path,
                    width=width,
                    height=height,
                    duration=duration_sec,
                    frame_count=frame_count,
                    fps=fps,
                    format="gif",
                )
            else:
                # Static image
                return MediaInfo(
                    path=path,
                    width=width,
                    height=height,
                    duration=0,
                    frame_count=1,
                    fps=0,
                    format="image",
                )
    except Exception:
        pass

    # Try ffprobe for videos
    probe_data = _run_ffprobe(path)
    if probe_data:
        video_stream = None
        for stream in probe_data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        if video_stream:
            width = video_stream.get("width", 0)
            height = video_stream.get("height", 0)
            codec = video_stream.get("codec_name", "unknown")

            # Get duration
            duration = 0
            if "duration" in video_stream:
                duration = float(video_stream["duration"])
            elif "duration" in probe_data.get("format", {}):
                duration = float(probe_data["format"]["duration"])

            # Get frame count and fps
            frame_count = int(video_stream.get("nb_frames", 0))
            fps_str = video_stream.get("r_frame_rate", "30/1")
            try:
                if "/" in fps_str:
                    num, den = fps_str.split("/")
                    fps = float(num) / float(den) if float(den) != 0 else 30.0
                else:
                    fps = float(fps_str)
            except (ValueError, ZeroDivisionError):
                fps = 30.0

            # Estimate frame count if not available
            if frame_count == 0 and duration > 0:
                frame_count = int(duration * fps)

            return MediaInfo(
                path=path,
                width=width,
                height=height,
                duration=duration,
                frame_count=frame_count,
                fps=fps,
                format="gif" if codec == "gif" else "video",
                codec=codec,
            )

    return None


def extract_frames_gif(
    gif_path: str,
    output_dir: str,
    num_frames: int = 6,
    prefix: str = "frame",
) -> List[str]:
    """
    Extract frames from a GIF using PIL.

    Args:
        gif_path: Path to GIF file
        output_dir: Directory to save frames
        num_frames: Number of frames to extract
        prefix: Filename prefix for output frames

    Returns:
        List of paths to extracted frames
    """
    os.makedirs(output_dir, exist_ok=True)
    output_paths = []

    with Image.open(gif_path) as img:
        # Count total frames
        total_frames = 0
        try:
            while True:
                total_frames += 1
                img.seek(img.tell() + 1)
        except EOFError:
            pass

        # Calculate which frames to extract (uniform distribution)
        if total_frames <= num_frames:
            frame_indices = list(range(total_frames))
        else:
            step = total_frames / num_frames
            frame_indices = [int(i * step) for i in range(num_frames)]

        # Extract selected frames
        img.seek(0)
        current_frame = 0
        extracted = 0

        for target_frame in frame_indices:
            # Seek to target frame
            while current_frame < target_frame:
                try:
                    img.seek(img.tell() + 1)
                    current_frame += 1
                except EOFError:
                    break

            # Save frame
            output_path = os.path.join(output_dir, f"{prefix}_{extracted + 1:03d}.png")

            # Convert to RGB if necessary (GIFs can have palette mode)
            frame = img.convert("RGBA")

            # Create white background for transparency
            background = Image.new("RGBA", frame.size, (255, 255, 255, 255))
            background.paste(frame, mask=frame.split()[-1] if frame.mode == "RGBA" else None)
            background = background.convert("RGB")

            background.save(output_path, "PNG")
            output_paths.append(output_path)
            extracted += 1

            if extracted >= num_frames:
                break

    return output_paths


def extract_frames_video(
    video_path: str,
    output_dir: str,
    num_frames: int = 6,
    prefix: str = "frame",
) -> List[str]:
    """
    Extract frames from a video using ffmpeg.

    Args:
        video_path: Path to video file
        output_dir: Directory to save frames
        num_frames: Number of frames to extract
        prefix: Filename prefix for output frames

    Returns:
        List of paths to extracted frames
    """
    if not check_ffmpeg():
        raise RuntimeError("ffmpeg is required for video extraction. Please install it.")

    os.makedirs(output_dir, exist_ok=True)

    # Get video info to calculate frame positions
    info = get_media_info(video_path)
    if not info:
        raise ValueError(f"Could not read video info: {video_path}")

    output_pattern = os.path.join(output_dir, f"{prefix}_%03d.png")
    output_paths = []

    if info.duration <= 0:
        # For very short videos or unknown duration, extract first frames
        cmd = [
            "ffmpeg",
            "-i",
            video_path,
            "-vf",
            f"select='lt(n\\,{num_frames})'",
            "-vsync",
            "vfr",
            "-frames:v",
            str(num_frames),
            "-y",
            output_pattern,
        ]
    else:
        # Calculate FPS to get desired number of frames
        target_fps = num_frames / info.duration
        # Use a minimum of 0.1 fps to avoid issues
        target_fps = max(0.1, target_fps)

        cmd = [
            "ffmpeg",
            "-i",
            video_path,
            "-vf",
            f"fps={target_fps}",
            "-frames:v",
            str(num_frames),
            "-y",
            output_pattern,
        ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=120,
        )

        # Collect output files
        for i in range(1, num_frames + 1):
            frame_path = os.path.join(output_dir, f"{prefix}_{i:03d}.png")
            if os.path.exists(frame_path):
                output_paths.append(frame_path)

    except subprocess.TimeoutExpired:
        raise RuntimeError("Frame extraction timed out")

    return output_paths


def extract_frames(
    source_path: str,
    output_dir: str,
    num_frames: int = 6,
    prefix: str = "frame",
) -> Tuple[List[str], MediaInfo]:
    """
    Extract frames from any supported media (video, GIF, image).

    Args:
        source_path: Path to media file
        output_dir: Directory to save frames
        num_frames: Number of frames to extract
        prefix: Filename prefix for output frames

    Returns:
        Tuple of (list of frame paths, media info)
    """
    info = get_media_info(source_path)
    if not info:
        raise ValueError(f"Could not read media file: {source_path}")

    if info.format == "image" and not info.is_animated:
        # Static image - just copy it
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{prefix}_001.png")
        with Image.open(source_path) as img:
            img = img.convert("RGB")
            img.save(output_path, "PNG")
        return [output_path], info

    if info.format == "gif":
        paths = extract_frames_gif(source_path, output_dir, num_frames, prefix)
        return paths, info

    # Video
    paths = extract_frames_video(source_path, output_dir, num_frames, prefix)
    return paths, info


def download_url(url: str, output_dir: Optional[str] = None) -> str:
    """
    Download a video/GIF from URL.

    Args:
        url: URL to download
        output_dir: Where to save (uses temp dir if None)

    Returns:
        Path to downloaded file
    """
    import urllib.request
    from urllib.parse import urlparse

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="v2i_download_")

    # Determine filename from URL
    parsed = urlparse(url)
    filename = os.path.basename(parsed.path) or "download"

    # Add extension if missing
    if "." not in filename:
        # Guess from content-type later
        filename += ".mp4"

    output_path = os.path.join(output_dir, filename)

    # Download
    try:
        urllib.request.urlretrieve(url, output_path)
    except Exception as e:
        raise RuntimeError(f"Failed to download {url}: {e}")

    return output_path
