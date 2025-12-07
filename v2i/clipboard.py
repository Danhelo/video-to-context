"""Cross-platform clipboard handling for images and GIFs."""

import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

# Clipboard content types


def _escape_applescript_string(s: str) -> str:
    """Escape a string for use in AppleScript."""
    # Escape backslashes first, then double quotes
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _escape_powershell_string(s: str) -> str:
    """Escape a string for use in PowerShell double-quoted strings."""
    # Escape backticks, double quotes, and dollar signs
    return s.replace("`", "``").replace('"', '`"').replace("$", "`$")


CLIPBOARD_IMAGE = "image"
CLIPBOARD_GIF = "gif"
CLIPBOARD_FILE = "file"
CLIPBOARD_EMPTY = "empty"


def get_platform() -> str:
    """Get current platform: 'darwin', 'linux', or 'windows'."""
    system = platform.system().lower()
    if system == "darwin":
        return "darwin"
    elif system == "linux":
        return "linux"
    elif system == "windows":
        return "windows"
    return "unknown"


def _run_command(cmd: list, capture_output: bool = True) -> Tuple[int, bytes, bytes]:
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            timeout=10,
        )
        return result.returncode, result.stdout, result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return 1, b"", str(e).encode()


def _check_tool_available(tool: str) -> bool:
    """Check if a command-line tool is available."""
    return shutil.which(tool) is not None


# =============================================================================
# macOS Clipboard
# =============================================================================


def _macos_get_clipboard_type() -> str:
    """Detect what type of content is in macOS clipboard."""
    # Check for file paths first (files copied in Finder)
    script = """
    tell application "System Events"
        try
            set clipClass to (class of (the clipboard as record))
            return clipClass as string
        end try
    end tell
    return ""
    """

    # Try to get file paths
    script_files = 'the clipboard as «class furl»'
    ret, stdout, _ = _run_command(["osascript", "-e", script_files])
    if ret == 0 and stdout.strip():
        file_path = stdout.decode().strip()
        # Clean up the file:// prefix if present
        if "file://" in file_path or file_path.endswith((".gif", ".GIF")):
            return CLIPBOARD_FILE

    # Check for GIF data directly
    script_gif = 'the clipboard as «class GIFf»'
    ret, stdout, _ = _run_command(["osascript", "-e", script_gif])
    if ret == 0 and stdout:
        return CLIPBOARD_GIF

    # Check for PNG/image data
    script_png = 'the clipboard as «class PNGf»'
    ret, stdout, _ = _run_command(["osascript", "-e", script_png])
    if ret == 0 and stdout:
        return CLIPBOARD_IMAGE

    # Check for TIFF (common macOS image format)
    script_tiff = 'the clipboard as «class TIFF»'
    ret, stdout, _ = _run_command(["osascript", "-e", script_tiff])
    if ret == 0 and stdout:
        return CLIPBOARD_IMAGE

    return CLIPBOARD_EMPTY


def _macos_get_file_path() -> Optional[str]:
    """Get file path from macOS clipboard."""
    # Try different approaches to get file path

    # Method 1: Direct file URL
    script = """
    set theFile to the clipboard as «class furl»
    return POSIX path of theFile
    """
    ret, stdout, _ = _run_command(["osascript", "-e", script])
    if ret == 0 and stdout.strip():
        path = stdout.decode().strip()
        if os.path.exists(path):
            return path

    # Method 2: File list
    script = """
    set fileList to the clipboard as list
    if (count of fileList) > 0 then
        set firstFile to item 1 of fileList
        if class of firstFile is alias then
            return POSIX path of firstFile
        end if
    end if
    return ""
    """
    ret, stdout, _ = _run_command(["osascript", "-e", script])
    if ret == 0 and stdout.strip():
        path = stdout.decode().strip()
        if os.path.exists(path):
            return path

    return None


def _macos_save_clipboard_image(output_path: str, as_gif: bool = False) -> bool:
    """Save clipboard image/GIF to file on macOS."""
    safe_path = _escape_applescript_string(output_path)

    if as_gif:
        # Try to get GIF data
        script = f"""
        set gifData to the clipboard as «class GIFf»
        set outFile to open for access POSIX file "{safe_path}" with write permission
        write gifData to outFile
        close access outFile
        """
        ret, _, _ = _run_command(["osascript", "-e", script])
        if ret == 0 and os.path.exists(output_path):
            return True

    # Try pngpaste if available (more reliable for images)
    if _check_tool_available("pngpaste"):
        ret, _, _ = _run_command(["pngpaste", output_path])
        if ret == 0 and os.path.exists(output_path):
            return True

    # Fallback to osascript for PNG
    script = f"""
    set pngData to the clipboard as «class PNGf»
    set outFile to open for access POSIX file "{safe_path}" with write permission
    write pngData to outFile
    close access outFile
    """
    ret, _, _ = _run_command(["osascript", "-e", script])
    return ret == 0 and os.path.exists(output_path)


# =============================================================================
# Linux Clipboard (X11 and Wayland)
# =============================================================================


def _linux_is_wayland() -> bool:
    """Check if running under Wayland."""
    return os.environ.get("WAYLAND_DISPLAY") is not None


def _linux_get_clipboard_type() -> str:
    """Detect what type of content is in Linux clipboard."""
    if _linux_is_wayland():
        return _linux_wayland_get_clipboard_type()
    return _linux_x11_get_clipboard_type()


def _linux_x11_get_clipboard_type() -> str:
    """Get clipboard type for X11."""
    if not _check_tool_available("xclip"):
        return CLIPBOARD_EMPTY

    # Get available targets
    ret, stdout, _ = _run_command(["xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"])
    if ret != 0:
        return CLIPBOARD_EMPTY

    targets = stdout.decode().lower()

    # Check for file paths
    if "text/uri-list" in targets:
        ret, stdout, _ = _run_command(
            ["xclip", "-selection", "clipboard", "-t", "text/uri-list", "-o"]
        )
        if ret == 0:
            uri = stdout.decode().strip()
            if uri.startswith("file://") and (".gif" in uri.lower() or os.path.exists(uri[7:])):
                return CLIPBOARD_FILE

    # Check for GIF
    if "image/gif" in targets:
        return CLIPBOARD_GIF

    # Check for other images
    if any(t in targets for t in ["image/png", "image/jpeg", "image/bmp"]):
        return CLIPBOARD_IMAGE

    return CLIPBOARD_EMPTY


def _linux_wayland_get_clipboard_type() -> str:
    """Get clipboard type for Wayland."""
    if not _check_tool_available("wl-paste"):
        return CLIPBOARD_EMPTY

    # Get available types
    ret, stdout, _ = _run_command(["wl-paste", "--list-types"])
    if ret != 0:
        return CLIPBOARD_EMPTY

    types = stdout.decode().lower()

    if "text/uri-list" in types:
        ret, stdout, _ = _run_command(["wl-paste", "--type", "text/uri-list"])
        if ret == 0:
            uri = stdout.decode().strip()
            if uri.startswith("file://") and ".gif" in uri.lower():
                return CLIPBOARD_FILE

    if "image/gif" in types:
        return CLIPBOARD_GIF

    if any(t in types for t in ["image/png", "image/jpeg", "image/bmp"]):
        return CLIPBOARD_IMAGE

    return CLIPBOARD_EMPTY


def _linux_get_file_path() -> Optional[str]:
    """Get file path from Linux clipboard."""
    if _linux_is_wayland():
        cmd = ["wl-paste", "--type", "text/uri-list"]
    else:
        cmd = ["xclip", "-selection", "clipboard", "-t", "text/uri-list", "-o"]

    ret, stdout, _ = _run_command(cmd)
    if ret == 0:
        uri = stdout.decode().strip().split("\n")[0]  # First file only
        if uri.startswith("file://"):
            path = uri[7:]  # Remove file:// prefix
            # Handle URL encoding
            from urllib.parse import unquote
            path = unquote(path)
            if os.path.exists(path):
                return path
    return None


def _linux_save_clipboard_image(output_path: str, as_gif: bool = False) -> bool:
    """Save clipboard image/GIF to file on Linux."""
    mime_type = "image/gif" if as_gif else "image/png"

    if _linux_is_wayland():
        cmd = ["wl-paste", "--type", mime_type]
    else:
        cmd = ["xclip", "-selection", "clipboard", "-t", mime_type, "-o"]

    ret, stdout, _ = _run_command(cmd)
    if ret == 0 and stdout:
        with open(output_path, "wb") as f:
            f.write(stdout)
        return True
    return False


# =============================================================================
# Windows Clipboard
# =============================================================================


def _windows_get_clipboard_type() -> str:
    """Detect what type of content is in Windows clipboard."""
    # Use PowerShell to check clipboard
    script = """
    Add-Type -AssemblyName System.Windows.Forms
    $cb = [System.Windows.Forms.Clipboard]
    if ($cb::ContainsFileDropList()) { Write-Output "file" }
    elseif ($cb::ContainsImage()) { Write-Output "image" }
    else { Write-Output "empty" }
    """
    ret, stdout, _ = _run_command(["powershell", "-Command", script])
    if ret == 0:
        result = stdout.decode().strip().lower()
        if result == "file":
            # Check if it's a GIF file
            files = _windows_get_file_paths()
            if files and files[0].lower().endswith(".gif"):
                return CLIPBOARD_FILE
            return CLIPBOARD_FILE
        elif result == "image":
            return CLIPBOARD_IMAGE
    return CLIPBOARD_EMPTY


def _windows_get_file_paths() -> list:
    """Get file paths from Windows clipboard."""
    script = """
    Add-Type -AssemblyName System.Windows.Forms
    $files = [System.Windows.Forms.Clipboard]::GetFileDropList()
    foreach ($f in $files) { Write-Output $f }
    """
    ret, stdout, _ = _run_command(["powershell", "-Command", script])
    if ret == 0:
        return [p for p in stdout.decode().strip().split("\n") if p and os.path.exists(p)]
    return []


def _windows_get_file_path() -> Optional[str]:
    """Get first file path from Windows clipboard."""
    paths = _windows_get_file_paths()
    return paths[0] if paths else None


def _windows_save_clipboard_image(output_path: str, as_gif: bool = False) -> bool:
    """Save clipboard image to file on Windows."""
    safe_path = _escape_powershell_string(output_path)
    # GIF from clipboard on Windows is tricky - usually comes as file
    script = f"""
    Add-Type -AssemblyName System.Windows.Forms
    $img = [System.Windows.Forms.Clipboard]::GetImage()
    if ($img -ne $null) {{
        $img.Save("{safe_path}")
        Write-Output "saved"
    }}
    """
    ret, stdout, _ = _run_command(["powershell", "-Command", script])
    return ret == 0 and b"saved" in stdout


# =============================================================================
# Public API
# =============================================================================


def get_clipboard_content_type() -> str:
    """
    Detect what type of content is in the clipboard.

    Returns one of: CLIPBOARD_IMAGE, CLIPBOARD_GIF, CLIPBOARD_FILE, CLIPBOARD_EMPTY
    """
    plat = get_platform()
    if plat == "darwin":
        return _macos_get_clipboard_type()
    elif plat == "linux":
        return _linux_get_clipboard_type()
    elif plat == "windows":
        return _windows_get_clipboard_type()
    return CLIPBOARD_EMPTY


def get_clipboard_file_path() -> Optional[str]:
    """Get file path if clipboard contains a file reference."""
    plat = get_platform()
    if plat == "darwin":
        return _macos_get_file_path()
    elif plat == "linux":
        return _linux_get_file_path()
    elif plat == "windows":
        return _windows_get_file_path()
    return None


def save_clipboard_to_file(output_path: Optional[str] = None, as_gif: bool = False) -> Optional[str]:
    """
    Save clipboard image/GIF content to a file.

    Args:
        output_path: Where to save. If None, creates temp file.
        as_gif: If True, try to save as GIF format.

    Returns:
        Path to saved file, or None if failed.
    """
    if output_path is None:
        ext = ".gif" if as_gif else ".png"
        fd, output_path = tempfile.mkstemp(suffix=ext, prefix="v2i_clipboard_")
        os.close(fd)

    plat = get_platform()
    success = False

    if plat == "darwin":
        success = _macos_save_clipboard_image(output_path, as_gif)
    elif plat == "linux":
        success = _linux_save_clipboard_image(output_path, as_gif)
    elif plat == "windows":
        success = _windows_save_clipboard_image(output_path, as_gif)

    if success and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        return output_path

    # Clean up failed attempt
    if os.path.exists(output_path):
        os.remove(output_path)
    return None


def get_clipboard_for_extraction() -> Tuple[Optional[str], str]:
    """
    Get clipboard content ready for frame extraction.

    Returns:
        Tuple of (file_path, content_type) where:
        - file_path: Path to file (existing or temp)
        - content_type: One of the CLIPBOARD_* constants
    """
    content_type = get_clipboard_content_type()

    if content_type == CLIPBOARD_EMPTY:
        return None, CLIPBOARD_EMPTY

    if content_type == CLIPBOARD_FILE:
        # It's a file reference - get the path
        path = get_clipboard_file_path()
        if path:
            return path, CLIPBOARD_FILE
        return None, CLIPBOARD_EMPTY

    if content_type == CLIPBOARD_GIF:
        # Save GIF data to temp file
        path = save_clipboard_to_file(as_gif=True)
        if path:
            return path, CLIPBOARD_GIF
        return None, CLIPBOARD_EMPTY

    if content_type == CLIPBOARD_IMAGE:
        # Save image data to temp file
        path = save_clipboard_to_file(as_gif=False)
        if path:
            return path, CLIPBOARD_IMAGE
        return None, CLIPBOARD_EMPTY

    return None, CLIPBOARD_EMPTY


def check_clipboard_tools() -> dict:
    """
    Check which clipboard tools are available on the system.

    Returns:
        Dict with tool availability status.
    """
    plat = get_platform()
    result = {"platform": plat, "tools": {}, "ready": False}

    if plat == "darwin":
        result["tools"]["osascript"] = _check_tool_available("osascript")
        result["tools"]["pngpaste"] = _check_tool_available("pngpaste")
        result["ready"] = result["tools"]["osascript"]

    elif plat == "linux":
        is_wayland = _linux_is_wayland()
        result["display_server"] = "wayland" if is_wayland else "x11"
        if is_wayland:
            result["tools"]["wl-paste"] = _check_tool_available("wl-paste")
            result["ready"] = result["tools"]["wl-paste"]
        else:
            result["tools"]["xclip"] = _check_tool_available("xclip")
            result["ready"] = result["tools"]["xclip"]

    elif plat == "windows":
        result["tools"]["powershell"] = _check_tool_available("powershell")
        result["ready"] = result["tools"]["powershell"]

    return result
