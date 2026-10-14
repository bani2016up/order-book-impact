#!/usr/bin/env python3
"""Render this gallery's basic Excalidraw shapes as portable SVG previews.

Only the documented rectangle/ellipse/line/arrow/text subset is supported.
This is a deterministic preview renderer, not the full Excalidraw exporter.
Use Excalidraw's SVG export for hand-drawn styling or additional element types.
"""
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def validate(data: dict) -> list[dict]:
    if data.get("type") != "excalidraw" or data.get("version") != 2:
        raise ValueError("Expected an Excalidraw v2 scene")
    elements = [e for e in data["elements"] if not e.get("isDeleted")]
    ids = [e["id"] for e in elements]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate element IDs")
    for e in elements:
        if e["type"] not in {"rectangle", "ellipse", "line", "arrow", "text"}:
            raise ValueError(f"Unsupported preview element: {e['type']}")
        if e.get("angle", 0) != 0:
            raise ValueError("Rotated elements require Excalidraw's native export")
        for field in ("x", "y", "width", "height"):
            if not math.isfinite(e[field]):
                raise ValueError(f"Invalid coordinate: {e['id']}")
        if e["type"] == "text":
            if e["fontFamily"] != 5 or e["fontSize"] < 16:
                raise ValueError("Gallery text requires Excalifont and font size >=16")
        if e["type"] in {"arrow", "line"} and len(e["points"]) < 2:
            raise ValueError("An edge requires at least two points")
    return elements


def render(path: Path, *, check: bool) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    elements = validate(data)
    bounds = []
    for e in elements:
        if e["type"] in {"arrow", "line"}:
            points = [(e["x"] + px, e["y"] + py) for px, py in e["points"]]
            bounds.extend(points)
        else:
            bounds.extend([(e["x"], e["y"]),
                           (e["x"] + e["width"], e["y"] + e["height"])])
    xmin = min(x for x, _ in bounds) - 25
    ymin = min(y for _, y in bounds) - 25
    xmax = max(x for x, _ in bounds) + 25
    ymax = max(y for _, y in bounds) + 25
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{number(xmax-xmin)}" height="{number(ymax-ymin)}" '
        f'viewBox="{number(xmin)} {number(ymin)} {number(xmax-xmin)} {number(ymax-ymin)}" '
        'role="img">',
        f"<title>{escape(elements[0].get('text', path.stem))}</title>",
        "<desc>Local order-book impact toolkit implementation diagram. "
        "Editable Excalidraw source is provided alongside this preview.</desc>",
        f'<rect x="{number(xmin)}" y="{number(ymin)}" width="{number(xmax-xmin)}" '
        f'height="{number(ymax-ymin)}" fill="#ffffff"/>',
    ]
    for e in elements:
        x, y, w, h = (e[field] for field in ("x", "y", "width", "height"))
        stroke = escape(e["strokeColor"])
        fill = escape(e.get("backgroundColor", "transparent"))
        if fill == "transparent":
            fill = "none"
        dash = {"dashed": "8 6", "dotted": "2 5"}.get(e.get("strokeStyle"))
        style = f'stroke="{stroke}" stroke-width="{e["strokeWidth"]}" fill="{fill}"'
        if dash:
            style += f' stroke-dasharray="{dash}"'
        if e["type"] == "rectangle":
            parts.append(f'<rect x="{number(x)}" y="{number(y)}" width="{number(w)}" '
                         f'height="{number(h)}" rx="{12 if e.get("roundness") else 0}" {style}/>')
        elif e["type"] == "ellipse":
            parts.append(f'<ellipse cx="{number(x+w/2)}" cy="{number(y+h/2)}" '
                         f'rx="{number(w/2)}" ry="{number(h/2)}" {style}/>')
        elif e["type"] in {"line", "arrow"}:
            points = [(x + px, y + py) for px, py in e["points"]]
            polyline = " ".join(f"{number(px)},{number(py)}" for px, py in points)
            parts.append(f'<polyline points="{polyline}" {style}/>')
            if e["type"] == "arrow" and e.get("endArrowhead"):
                tip, previous = points[-1], points[-2]
                angle = math.atan2(tip[1]-previous[1], tip[0]-previous[0])
                left = (tip[0]-12*math.cos(angle-0.45), tip[1]-12*math.sin(angle-0.45))
                right = (tip[0]-12*math.cos(angle+0.45), tip[1]-12*math.sin(angle+0.45))
                head = " ".join(f"{number(px)},{number(py)}" for px, py in (left, tip, right))
                parts.append(f'<polyline points="{head}" fill="none" stroke="{stroke}" stroke-width="1.6"/>')
        else:
            size = e["fontSize"]
            lines = e["text"].split("\n")
            parts.append(f'<text fill="{stroke}" font-family="Arial, Helvetica, sans-serif" '
                         f'font-size="{size}" xml:space="preserve">')
            for i, line in enumerate(lines):
                parts.append(f'<tspan x="{number(x)}" y="{number(y+size+i*size*e.get("lineHeight", 1.3))}">'
                             f'{escape(line)}</tspan>')
            parts.append("</text>")
    parts.append("</svg>")
    svg = "\n".join(parts) + "\n"
    output = path.with_suffix(".svg")
    if check:
        if not output.exists() or output.read_text(encoding="utf-8") != svg:
            raise ValueError(f"Preview is stale: {output.name}")
    else:
        output.write_text(svg, encoding="utf-8")
    print(f"{path.name}: {len(elements)} elements; {'checked' if check else 'rendered'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate scenes and verify committed previews")
    args = parser.parse_args()
    for path in sorted(ROOT.glob("*.excalidraw")):
        render(path, check=args.check)


if __name__ == "__main__":
    main()
