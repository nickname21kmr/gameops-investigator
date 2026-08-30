from __future__ import annotations

from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = PROJECT_ROOT / "docs" / "demo"
OUTPUT = PROJECT_ROOT / "docs" / "demo.gif"


def build() -> Path:
    sources = [
        DEMO_DIR / "investigation.png",
        DEMO_DIR / "monitoring.png",
        DEMO_DIR / "evaluation.png",
    ]
    missing = [path for path in sources if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing browser-verified screenshots: {missing}")
    frames = []
    for path in sources:
        image = Image.open(path).convert("RGB")
        image.thumbnail((1280, 720), Image.Resampling.LANCZOS)
        frames.append(image.quantize(colors=192, method=Image.Quantize.MEDIANCUT))
    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=[2600, 2600, 3000],
        loop=0,
        optimize=True,
        disposal=2,
    )
    return OUTPUT


if __name__ == "__main__":
    print(build())

