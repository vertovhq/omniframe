"""Mean color and brightness of the given frames.

Args: {"project": "my-video", "images": ["renders/video-stills-9x16-0.jpg"]}

Relative image paths are read from the project folder, or from the output folder when no
project is given. Prints {"frames": [{"path", "width", "height", "mean_rgb", "brightness"}]}.
brightness is the mean luma from 0 (black) to 1 (white), using the ITU-R BT.601 weights.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

LUMA_WEIGHTS = np.array([0.299, 0.587, 0.114])


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: frame_stats.py <args.json>")
    args = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    images = args.get("images")
    if not isinstance(images, list) or not images:
        raise SystemExit("frame_stats: 'images' must be a non-empty list of file paths")

    frames = []
    for item in images:
        path = Path(str(item))
        if not path.is_file():
            raise SystemExit(f"frame_stats: not a file: {path}")
        with Image.open(path) as img:
            width, height = img.size
            pixels = np.asarray(img.convert("RGB"), dtype=np.float64).reshape(-1, 3)
        frames.append({
            "path": str(item),
            "width": width,
            "height": height,
            "mean_rgb": [round(float(v), 1) for v in pixels.mean(axis=0)],
            "brightness": round(float((pixels @ LUMA_WEIGHTS).mean()) / 255, 3),
        })
    print(json.dumps({"frames": frames}, ensure_ascii=False))


if __name__ == "__main__":
    main()
