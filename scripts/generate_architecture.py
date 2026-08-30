from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "docs" / "architecture.png"
WIDTH, HEIGHT = 1800, 1040
BACKGROUND = "#07111F"
PANEL = "#0E1B2B"
PANEL_ALT = "#102536"
TEXT = "#E7EEF7"
MUTED = "#9FB0C6"
TEAL = "#2DD4BF"
BLUE = "#60A5FA"
AMBER = "#FBBF24"
RED = "#FB7185"


def font(size: int, bold: bool = False):
    candidates = [
        Path("C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


TITLE = font(54, True)
SUBTITLE = font(24)
HEADER = font(25, True)
BODY = font(20)
SMALL = font(17)


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str, lines: list[str], accent: str = TEAL):
    draw.rounded_rectangle(box, radius=22, fill=PANEL, outline="#26384D", width=2)
    x1, y1, x2, _ = box
    draw.rounded_rectangle((x1, y1, x1 + 9, box[3]), radius=5, fill=accent)
    draw.text((x1 + 30, y1 + 22), title, font=HEADER, fill=TEXT)
    y = y1 + 63
    for line in lines:
        draw.text((x1 + 30, y), line, font=SMALL, fill=MUTED)
        y += 29


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color: str = TEAL):
    draw.line((start, end), fill=color, width=4)
    ex, ey = end
    sx, sy = start
    if abs(ex - sx) >= abs(ey - sy):
        direction = 1 if ex > sx else -1
        points = [(ex, ey), (ex - 14 * direction, ey - 8), (ex - 14 * direction, ey + 8)]
    else:
        direction = 1 if ey > sy else -1
        points = [(ex, ey), (ex - 8, ey - 14 * direction), (ex + 8, ey - 14 * direction)]
    draw.polygon(points, fill=color)


def generate() -> Path:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.text((70, 44), "GameOps Investigator", font=TITLE, fill=TEXT)
    draw.text((72, 112), "The model plans and explains. Deterministic programs own facts, calculations, and evidence.", font=SUBTITLE, fill=MUTED)

    rounded(draw, (70, 200, 470, 390), "1 · Investigation entry", ["Metric alert", "Analyst question", "Reproducible incident"], BLUE)
    rounded(draw, (570, 175, 1020, 325), "2A · Claude Code", ["Open-ended planning", "MCP tool selection", "Uncertainty-aware explanation"], TEAL)
    rounded(draw, (570, 340, 1020, 475), "2B · Deterministic replay", ["Offline demo and tests", "Same tool functions", "No LLM impersonation"], AMBER)
    rounded(draw, (1120, 200, 1730, 445), "3 · Read-only MCP surface", ["get_metric_definition", "query_metrics", "compare_cohorts", "detect_anomalies", "draft_incident_report"], TEAL)

    rounded(draw, (70, 570, 470, 830), "4 · Data contract", ["Canonical users + events", "Metric catalog", "Synthetic source snapshot", "Derived incident database", "Ground truth blocked"], BLUE)
    rounded(draw, (570, 545, 1020, 855), "5 · Deterministic core", ["SQLite read-only authorizer", "Row + timeout limits", "Cohort contribution", "Two-proportion z test", "Log rate-ratio test", "Evidence SHA-256"], TEAL)
    rounded(draw, (1120, 570, 1730, 830), "6 · Review and evaluation", ["Ranked Top-3 candidates", "SQL evidence ledger", "Human-review report", "40 fixed eval cases", "Measured latency; cost N/A until run"], RED)

    arrow(draw, (470, 265), (570, 240), BLUE)
    arrow(draw, (470, 325), (570, 405), AMBER)
    arrow(draw, (1020, 240), (1120, 275), TEAL)
    arrow(draw, (1020, 405), (1120, 365), AMBER)
    arrow(draw, (1425, 445), (1425, 570), TEAL)
    arrow(draw, (470, 700), (570, 700), BLUE)
    arrow(draw, (1020, 700), (1120, 700), TEAL)
    arrow(draw, (820, 545), (820, 475), TEAL)

    draw.text((72, 930), "Portable boundary", font=HEADER, fill=TEAL)
    draw.text((310, 934), "Swap the warehouse or LLM host without changing the metric, safety, evidence, and review contracts.", font=BODY, fill=MUTED)
    draw.text((72, 982), "Synthetic demo · read-only · human approval required", font=SMALL, fill="#7DD3FC")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, format="PNG", optimize=True)
    return OUTPUT


if __name__ == "__main__":
    try:
        print(generate())
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise
