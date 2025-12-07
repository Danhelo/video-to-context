"""CLI interface for v2i."""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from v2i import __version__
from v2i.clipboard import (
    CLIPBOARD_EMPTY,
    CLIPBOARD_FILE,
    CLIPBOARD_GIF,
    CLIPBOARD_IMAGE,
    check_clipboard_tools,
    get_clipboard_for_extraction,
)
from v2i.extractor import (
    check_ffmpeg,
    download_url,
    extract_frames,
    get_media_info,
)
from v2i.optimizer import (
    format_file_size,
    get_file_size,
    get_total_size,
    optimize_frames,
)


# ANSI colors (disabled on Windows unless in modern terminal)
def supports_color() -> bool:
    """Check if terminal supports ANSI colors."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if platform.system() == "Windows":
        # Check for modern Windows terminal
        return os.environ.get("WT_SESSION") is not None
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


USE_COLOR = supports_color()


def style(text: str, code: str) -> str:
    """Apply ANSI style if supported."""
    if not USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def green(text: str) -> str:
    return style(text, "32")


def yellow(text: str) -> str:
    return style(text, "33")


def blue(text: str) -> str:
    return style(text, "34")


def dim(text: str) -> str:
    return style(text, "2")


def bold(text: str) -> str:
    return style(text, "1")


def validate_quality(value: str) -> int:
    """Validate quality argument is between 1 and 100."""
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid int value: '{value}'")
    if ivalue < 1 or ivalue > 100:
        raise argparse.ArgumentTypeError(f"quality must be between 1 and 100, got {ivalue}")
    return ivalue


def validate_max_size(value: str) -> int:
    """Validate max-size argument is positive and reasonable."""
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid int value: '{value}'")
    if ivalue < 16:
        raise argparse.ArgumentTypeError(f"max-size must be at least 16 pixels, got {ivalue}")
    if ivalue > 16384:
        raise argparse.ArgumentTypeError(f"max-size must be at most 16384 pixels, got {ivalue}")
    return ivalue


def validate_frames(value: str) -> int:
    """Validate frames argument is positive."""
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid int value: '{value}'")
    if ivalue < 1:
        raise argparse.ArgumentTypeError(f"frames must be at least 1, got {ivalue}")
    return ivalue


def print_error(msg: str) -> None:
    """Print error message."""
    print(f"{style('Error:', '31;1')} {msg}", file=sys.stderr)


def print_warning(msg: str) -> None:
    """Print warning message."""
    print(f"{yellow('Warning:')} {msg}", file=sys.stderr)


def print_success(msg: str) -> None:
    """Print success message."""
    print(f"{green('✓')} {msg}")


def open_folder(path: str) -> None:
    """Open folder in system file manager."""
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", path], check=False)
        elif system == "Windows":
            subprocess.run(["explorer", path], check=False)
        else:  # Linux
            subprocess.run(["xdg-open", path], check=False)
    except Exception:
        pass


def is_url(source: str) -> bool:
    """Check if source looks like a URL."""
    return source.startswith(("http://", "https://"))


def detect_source(source: Optional[str]) -> tuple:
    """
    Detect and resolve the input source.

    Returns:
        Tuple of (resolved_path, source_type, is_temp)
        source_type: 'clipboard', 'url', 'file'
        is_temp: True if the file is temporary and should be cleaned up
    """
    if source is None or source == "--clipboard":
        # Clipboard mode
        path, content_type = get_clipboard_for_extraction()
        if content_type == CLIPBOARD_EMPTY or path is None:
            return None, "empty", False

        # If it's a file reference, it's not temp
        is_temp = content_type != CLIPBOARD_FILE
        return path, "clipboard", is_temp

    if is_url(source):
        # URL mode - download first
        print(f"Downloading from URL...")
        path = download_url(source)
        return path, "url", True

    # File mode
    if not os.path.exists(source):
        return None, "not_found", False

    return os.path.abspath(source), "file", False


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="v2i",
        description="Convert videos/GIFs to images for LLM prompts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  v2i                           Extract frames from clipboard (default)
  v2i video.mp4                 Extract from local video
  v2i animation.gif             Extract from local GIF
  v2i https://example.com/v.mp4 Extract from URL

Tip: Copy a GIF, run 'v2i', then drag frames into Claude Code!
        """,
    )

    parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help="Video/GIF file, URL, or --clipboard (default: clipboard)",
    )

    parser.add_argument(
        "-n",
        "--frames",
        type=validate_frames,
        default=6,
        metavar="N",
        help="Number of frames to extract (default: 6)",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="./v2i_frames",
        metavar="DIR",
        help="Output directory (default: ./v2i_frames)",
    )

    parser.add_argument(
        "-s",
        "--max-size",
        type=validate_max_size,
        default=1024,
        metavar="PX",
        help="Max dimension in pixels (default: 1024)",
    )

    parser.add_argument(
        "-f",
        "--format",
        type=str,
        choices=["jpg", "png", "webp"],
        default="jpg",
        help="Output format (default: jpg)",
    )

    parser.add_argument(
        "-q",
        "--quality",
        type=validate_quality,
        default=80,
        metavar="N",
        help="JPEG/WebP quality 1-100 (default: 80)",
    )

    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove previous frames before extracting",
    )

    parser.add_argument(
        "--open",
        action="store_true",
        help="Open output folder after extraction",
    )

    parser.add_argument(
        "--info",
        action="store_true",
        help="Show media info without extracting",
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Check system dependencies",
    )

    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"v2i {__version__}",
    )

    return parser


def check_dependencies() -> bool:
    """Check and report on system dependencies."""
    print(bold("v2i dependency check\n"))

    all_ok = True

    # Check ffmpeg
    ffmpeg_ok = check_ffmpeg()
    status = green("✓ installed") if ffmpeg_ok else yellow("✗ not found")
    print(f"  ffmpeg: {status}")
    if not ffmpeg_ok:
        print(dim("    Required for video extraction. Install: brew/apt/choco install ffmpeg"))
        all_ok = False

    # Check clipboard tools
    clip_info = check_clipboard_tools()
    print(f"\n  Platform: {clip_info['platform']}")

    if clip_info.get("display_server"):
        print(f"  Display: {clip_info['display_server']}")

    print("  Clipboard tools:")
    for tool, available in clip_info.get("tools", {}).items():
        status = green("✓") if available else yellow("✗")
        print(f"    {status} {tool}")

    if not clip_info.get("ready"):
        all_ok = False
        if clip_info["platform"] == "linux":
            ds = clip_info.get("display_server", "x11")
            if ds == "wayland":
                print(dim("    Install: sudo apt install wl-clipboard"))
            else:
                print(dim("    Install: sudo apt install xclip"))
        elif clip_info["platform"] == "darwin":
            print(dim("    Optional: brew install pngpaste (for better image support)"))

    print()
    if all_ok:
        print(green("All dependencies satisfied!"))
    else:
        print(yellow("Some optional dependencies missing (see above)"))

    return all_ok


def run_extraction(args: argparse.Namespace) -> int:
    """Run the main extraction workflow."""
    # Resolve source
    source_path, source_type, is_temp = detect_source(args.source)

    if source_type == "empty":
        print_error("Clipboard is empty or doesn't contain an image/GIF")
        print(dim("\nTip: Copy a GIF or image first, then run 'v2i'"))
        return 1

    if source_type == "not_found":
        print_error(f"File not found: {args.source}")
        return 1

    if source_path is None:
        print_error("Could not get media from source")
        return 1

    # Get media info
    info = get_media_info(source_path)
    if info is None:
        print_error(f"Could not read media file: {source_path}")
        return 1

    # Show what we detected
    source_label = {
        "clipboard": "clipboard",
        "url": "URL",
        "file": "file",
    }.get(source_type, "source")

    print(f"\n{blue('Source:')} {info} {dim(f'({source_label})')}")

    # Info-only mode
    if args.info:
        print(f"\n  Path: {source_path}")
        print(f"  Format: {info.format}")
        print(f"  Dimensions: {info.width}x{info.height}")
        print(f"  Duration: {info.duration:.2f}s")
        print(f"  Frames: {info.frame_count}")
        if info.fps > 0:
            print(f"  FPS: {info.fps:.1f}")
        if info.codec:
            print(f"  Codec: {info.codec}")
        return 0

    # Determine actual frame count
    num_frames = min(args.frames, info.frame_count) if info.frame_count > 0 else args.frames

    if info.duration > 0:
        interval = info.duration / num_frames
        print(f"{blue('Extracting:')} {num_frames} frames {dim(f'(1 every {interval:.1f}s)')}")
    else:
        print(f"{blue('Extracting:')} {num_frames} frames")

    # Clean output directory if requested
    output_dir = os.path.abspath(args.output)
    if args.clean and os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    # Create temp directory for raw frames
    temp_dir = tempfile.mkdtemp(prefix="v2i_temp_")

    try:
        # Extract frames
        raw_frames, _ = extract_frames(
            source_path,
            temp_dir,
            num_frames=num_frames,
            prefix="raw",
        )

        if not raw_frames:
            print_error("No frames were extracted")
            return 1

        # Optimize frames
        final_frames = optimize_frames(
            raw_frames,
            output_dir,
            max_size=args.max_size,
            output_format=args.format,
            quality=args.quality,
            prefix="frame",
        )

        # Report results
        total_size = get_total_size(final_frames)
        print_success(f"Saved {len(final_frames)} frames to {output_dir}/")
        print(f"   Total size: {format_file_size(total_size)}")
        print()

        # List frames
        for frame_path in final_frames:
            size = format_file_size(get_file_size(frame_path))
            name = os.path.basename(frame_path)
            print(f"   {dim(name)} {dim(f'({size})')}")

        print()
        print(dim(f"Tip: Drag these into Claude Code, or paste paths above"))

        # Open folder if requested
        if args.open:
            open_folder(output_dir)

    finally:
        # Cleanup temp directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        # Cleanup downloaded/temp source file
        if is_temp and source_path and os.path.exists(source_path):
            try:
                os.remove(source_path)
                # Also try to remove parent temp dir if it's in temp
                parent = os.path.dirname(source_path)
                if parent.startswith(tempfile.gettempdir()):
                    shutil.rmtree(parent, ignore_errors=True)
            except Exception:
                pass

    return 0


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Dependency check mode
    if args.check:
        return 0 if check_dependencies() else 1

    # Run extraction
    try:
        return run_extraction(args)
    except KeyboardInterrupt:
        print("\nCancelled")
        return 130
    except Exception as e:
        print_error(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
