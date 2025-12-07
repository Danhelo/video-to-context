# v2i - Video to Images for LLM Prompts

A lightweight CLI tool that converts videos and GIFs into a series of images, optimized for use in LLM conversations (like Claude Code).

## The Problem

LLMs like Claude Code support pasting images but not videos or GIFs. When you have a screen recording, animation, or video you want to discuss, you need to manually extract frames.

## The Solution

```bash
# Copy a GIF to clipboard, then:
v2i

# That's it! Frames are saved to ./v2i_frames/
```

## Installation

```bash
# Clone and install
git clone https://github.com/your-repo/v2i.git
cd v2i
pip install -e .

# Or with pipx (recommended)
pipx install .
```

### Dependencies

- **Python 3.8+**
- **Pillow** (installed automatically)
- **ffmpeg** (required for video extraction)
  ```bash
  # macOS
  brew install ffmpeg

  # Ubuntu/Debian
  sudo apt install ffmpeg

  # Windows
  choco install ffmpeg
  ```

### Clipboard Tools (for clipboard mode)

- **macOS**: Works out of the box (optional: `brew install pngpaste`)
- **Linux X11**: `sudo apt install xclip`
- **Linux Wayland**: `sudo apt install wl-clipboard`
- **Windows**: Works out of the box (PowerShell)

## Usage

### Basic Usage (Clipboard-First)

```bash
# Copy a GIF or video to clipboard, then:
v2i

# Output:
# Source: GIF 480x270, 89 frames, 4.5s (clipboard)
# Extracting: 6 frames (1 every 0.75s)
# ✓ Saved 6 frames to ./v2i_frames/
```

### From Files and URLs

```bash
v2i video.mp4                      # Local video
v2i animation.gif                  # Local GIF
v2i https://example.com/video.mp4  # From URL
```

### Options

```
-n, --frames N      Number of frames to extract (default: 6)
-o, --output DIR    Output directory (default: ./v2i_frames)
-s, --max-size PX   Max dimension in pixels (default: 1024)
-f, --format FMT    Output format: jpg/png/webp (default: jpg)
-q, --quality N     JPEG/WebP quality 1-100 (default: 80)
--clean             Remove previous frames before extracting
--open              Open output folder after extraction
--info              Show media info without extracting
--check             Check system dependencies
```

### Examples

```bash
# Extract 10 frames as PNG
v2i video.mp4 -n 10 -f png

# High quality, larger images
v2i video.mp4 -s 2048 -q 95

# Quick preview (fewer, smaller frames)
v2i video.mp4 -n 4 -s 512

# Clean previous output first
v2i --clean

# Just show video info
v2i video.mp4 --info
```

## Claude Code Integration

### Slash Command

This repo includes a Claude Code slash command. After installing v2i:

```
/v2i              # Extract from clipboard
/v2i video.mp4    # Extract from file
```

### Workflow

1. Copy a GIF (e.g., from a webpage or screen recording)
2. In Claude Code, run `/v2i` or just run `v2i` in terminal
3. Drag the extracted frames into your conversation
4. Discuss the video content with Claude!

## Why These Defaults?

| Setting | Default | Rationale |
|---------|---------|-----------|
| Frames | 6 | Good coverage without overwhelming context |
| Max size | 1024px | Balances detail vs. token cost |
| Format | JPG | 5-10x smaller than PNG, good enough quality |
| Quality | 80% | Good visual quality, reasonable file size |

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .
```

## License

MIT
