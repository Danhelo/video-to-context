---
description: Convert clipboard GIF/video to images for this conversation
allowed-tools:
  - Bash
  - Read
---

# Video/GIF to Images Converter

Extract frames from clipboard content (GIF, video) or a file for use in this conversation.

## Usage

Run v2i to extract frames from clipboard (default) or a specific file:

```bash
# From clipboard (copy a GIF first, then run this)
v2i

# From a specific file
v2i $ARGUMENTS
```

## Instructions

1. Run the v2i command using Bash
2. Report the results to the user
3. If frames were extracted successfully, let the user know they can now drag the images into the conversation or reference the file paths

```bash
cd $PWD && python -m v2i $ARGUMENTS
```

After running, summarize:
- Number of frames extracted
- Output location
- Total size
- Remind user they can drag files into Claude Code or reference the paths
