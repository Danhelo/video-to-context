"""Image optimization for LLM-friendly output."""

import os
from pathlib import Path
from typing import List, Literal, Tuple

from PIL import Image

# Output format type
OutputFormat = Literal["jpg", "jpeg", "png", "webp"]


def get_image_size(path: str) -> Tuple[int, int]:
    """Get image dimensions."""
    with Image.open(path) as img:
        return img.size


def get_file_size(path: str) -> int:
    """Get file size in bytes."""
    return os.path.getsize(path)


def format_file_size(size_bytes: int) -> str:
    """Format file size for display."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def resize_image(
    image: Image.Image,
    max_size: int,
) -> Image.Image:
    """
    Resize image to fit within max_size while maintaining aspect ratio.

    Args:
        image: PIL Image object
        max_size: Maximum dimension (width or height)

    Returns:
        Resized image (or original if already smaller)
    """
    width, height = image.size

    # Check if resize needed
    if width <= max_size and height <= max_size:
        return image

    # Calculate new size maintaining aspect ratio
    if width > height:
        new_width = max_size
        new_height = int(height * (max_size / width))
    else:
        new_height = max_size
        new_width = int(width * (max_size / height))

    # Use high-quality resampling
    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)


def optimize_image(
    input_path: str,
    output_path: str,
    max_size: int = 1024,
    output_format: OutputFormat = "jpg",
    quality: int = 80,
) -> str:
    """
    Optimize a single image for LLM use.

    Args:
        input_path: Path to input image
        output_path: Path for output image
        max_size: Maximum dimension in pixels
        output_format: Output format (jpg, png, webp)
        quality: JPEG/WebP quality (1-100)

    Returns:
        Path to optimized image
    """
    with Image.open(input_path) as img:
        # Convert to RGB if necessary (for JPEG output)
        if output_format in ("jpg", "jpeg") and img.mode in ("RGBA", "P", "LA"):
            # Create white background for transparency
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[-1])
            elif img.mode == "P" and "transparency" in img.info:
                img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        elif img.mode not in ("RGB", "RGBA", "L"):
            img = img.convert("RGB")

        # Resize if needed
        img = resize_image(img, max_size)

        # Save with appropriate settings
        save_kwargs = {}

        if output_format in ("jpg", "jpeg"):
            save_kwargs["format"] = "JPEG"
            save_kwargs["quality"] = quality
            save_kwargs["optimize"] = True
        elif output_format == "png":
            save_kwargs["format"] = "PNG"
            save_kwargs["optimize"] = True
        elif output_format == "webp":
            save_kwargs["format"] = "WEBP"
            save_kwargs["quality"] = quality
            save_kwargs["method"] = 6  # Slower but better compression

        img.save(output_path, **save_kwargs)

    return output_path


def optimize_frames(
    frame_paths: List[str],
    output_dir: str,
    max_size: int = 1024,
    output_format: OutputFormat = "jpg",
    quality: int = 80,
    prefix: str = "frame",
) -> List[str]:
    """
    Optimize multiple frames for LLM use.

    Args:
        frame_paths: List of input frame paths
        output_dir: Directory for output frames
        max_size: Maximum dimension in pixels
        output_format: Output format (jpg, png, webp)
        quality: JPEG/WebP quality (1-100)
        prefix: Filename prefix

    Returns:
        List of paths to optimized frames
    """
    os.makedirs(output_dir, exist_ok=True)
    output_paths = []

    ext = "jpg" if output_format == "jpeg" else output_format

    for i, input_path in enumerate(frame_paths, 1):
        output_path = os.path.join(output_dir, f"{prefix}_{i:03d}.{ext}")
        optimize_image(
            input_path,
            output_path,
            max_size=max_size,
            output_format=output_format,
            quality=quality,
        )
        output_paths.append(output_path)

    return output_paths


def get_total_size(paths: List[str]) -> int:
    """Get total file size for a list of files."""
    return sum(get_file_size(p) for p in paths if os.path.exists(p))


def estimate_token_cost(paths: List[str]) -> int:
    """
    Estimate approximate token cost for images.

    This is a rough estimate based on typical image token costs.
    Actual costs vary by model and provider.
    """
    total_pixels = 0
    for path in paths:
        if os.path.exists(path):
            w, h = get_image_size(path)
            total_pixels += w * h

    # Rough estimate: ~750 tokens per 1M pixels for typical vision models
    # This varies significantly by model
    return int(total_pixels * 750 / 1_000_000)
