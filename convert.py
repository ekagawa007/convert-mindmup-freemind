#!/usr/bin/env python3
"""Convert MindMup mind maps (.mup) to FreeMind format (.mm).

Usage:
    python convert.py <input_file_or_dir> <output_dir>
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Intermediate representation
# ---------------------------------------------------------------------------

@dataclass
class Node:
    """Format-agnostic mind map node."""
    text: str
    children: list[Node] = field(default_factory=list)
    # "left" or "right" — meaningful only on root's direct children in FreeMind
    position: str | None = None


# ---------------------------------------------------------------------------
# Parsers  (MindMup → Node)
# ---------------------------------------------------------------------------

def _parse_json_node(data: dict, is_root: bool = False) -> Node:
    """Recursively convert a MindMup JSON node dict to Node.

    MindMup key ordering:
      - Keys are numeric strings (may be negative or fractional, e.g. "-1", "1.5")
      - Negative keys appear on the LEFT branch at the root level
      - Sorted ascending by float value
    """
    text = data.get("title", "")
    ideas: dict = data.get("ideas", {}) or {}
    sorted_items = sorted(ideas.items(), key=lambda kv: float(kv[0]))

    children: list[Node] = []
    for key, child_data in sorted_items:
        child = _parse_json_node(child_data)
        if is_root:
            child.position = "left" if float(key) < 0 else "right"
        children.append(child)

    return Node(text=text, children=children)


def parse_mindmup_json(data: dict) -> Node:
    """Parse a MindMup JSON document (root dict) into a Node tree."""
    return _parse_json_node(data, is_root=True)


def _parse_xml_node_elem(elem: ET.Element) -> Node:
    """Recursively convert a <node> XML element to Node."""
    text = (
        elem.get("TEXT")
        or elem.get("text")
        or elem.get("LABEL")
        or elem.get("label")
        or elem.get("name")
        or ""
    )
    position = elem.get("POSITION") or elem.get("position") or None
    children = [
        _parse_xml_node_elem(child)
        for child in elem
        if child.tag.lower() == "node"
    ]
    return Node(text=text, children=children, position=position)


def parse_mindmup_xml(xml_root: ET.Element) -> Node:
    """Parse a MindMup legacy XML (or FreeMind XML) document into a Node tree.

    Handles both:
      - <map><node ...>...</node></map>  (FreeMind / legacy MindMup export)
      - <node ...>...</node>             (bare root)

    If root children have no POSITION attribute, auto-assigns:
      right = first ceil(n/2) children, left = the rest.
    """
    if xml_root.tag.lower() == "map":
        node_elem = next((c for c in xml_root if c.tag.lower() == "node"), None)
        root_node = _parse_xml_node_elem(node_elem) if node_elem is not None else Node(text="")
    else:
        root_node = _parse_xml_node_elem(xml_root)

    # Auto-assign POSITION when the XML carries none
    if root_node.children and not any(c.position for c in root_node.children):
        n = len(root_node.children)
        right_count = (n + 1) // 2
        for i, child in enumerate(root_node.children):
            child.position = "right" if i < right_count else "left"

    return root_node


def load_source(path: Path) -> Node:
    """Auto-detect MindMup JSON vs XML by file content and return a Node tree."""
    text = path.read_text(encoding="utf-8").lstrip()
    if text.startswith("{"):
        data = json.loads(text)
        return parse_mindmup_json(data)
    if text.startswith("<"):
        xml_root = ET.fromstring(text)
        return parse_mindmup_xml(xml_root)
    raise ValueError(
        f"Unrecognized format in '{path}': content starts with neither '{{' nor '<'"
    )


# ---------------------------------------------------------------------------
# Builder  (Node → FreeMind ElementTree)
# ---------------------------------------------------------------------------

def _build_elem(node: Node, parent: ET.Element) -> ET.Element:
    attribs: dict[str, str] = {"TEXT": node.text}
    if node.position:
        attribs["POSITION"] = node.position
    elem = ET.SubElement(parent, "node", attribs)
    for child in node.children:
        _build_elem(child, elem)
    return elem


def build_freemind(root: Node) -> ET.ElementTree:
    """Build a FreeMind XML ElementTree from a Node tree."""
    map_elem = ET.Element("map", {"version": "1.0.1"})
    _build_elem(root, map_elem)
    ET.indent(map_elem, space="  ")
    return ET.ElementTree(map_elem)


# ---------------------------------------------------------------------------
# File conversion
# ---------------------------------------------------------------------------

def convert_file(src: Path, out_dir: Path) -> Path:
    """Convert one MindMup file and write the resulting .mm to out_dir."""
    node = load_source(src)
    tree = build_freemind(node)
    out_path = out_dir / (src.stem + ".mm")
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _collect_sources(inp: Path) -> list[Path]:
    if inp.is_file():
        return [inp]
    # MindMup saves files without an extension, so include those alongside .mup/.json
    candidates = (
        sorted(inp.rglob("*.mup"))
        + sorted(inp.rglob("*.json"))
        + sorted(p for p in inp.rglob("*") if p.is_file() and p.suffix == "")
    )
    seen: set[Path] = set()
    result: list[Path] = []
    for p in candidates:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert MindMup (.mup) files to FreeMind (.mm) format."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Source .mup file or directory containing .mup files (searched recursively)",
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        type=Path,
        default=None,
        help="Destination directory for .mm files (default: same directory as input)",
    )
    args = parser.parse_args(argv)

    inp: Path = args.input
    if args.output_dir is None:
        out_dir = inp.parent if inp.is_file() else inp
    else:
        out_dir = args.output_dir

    if not inp.exists():
        print(f"Error: '{inp}' does not exist.", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    sources = _collect_sources(inp)
    if not sources:
        print(f"No .mup or .json files found in '{inp}'.")
        return 0

    ok = ng = 0
    for src in sources:
        try:
            out_path = convert_file(src, out_dir)
            print(f"  [OK]   {src} → {out_path}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  [WARN] {src}: {exc}", file=sys.stderr)
            ng += 1

    print(f"\nDone: {ok} converted, {ng} failed.")
    return 0 if ng == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
