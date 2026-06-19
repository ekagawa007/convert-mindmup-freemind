"""Tests for convert.py — MindMup → FreeMind conversion."""

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

# Make the project root importable when tests are run from any directory.
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from convert import (
    Node,
    build_freemind,
    convert_file,
    load_source,
    parse_mindmup_json,
    parse_mindmup_xml,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# parse_mindmup_json
# ---------------------------------------------------------------------------

class TestParseMindmupJson(unittest.TestCase):
    def _simple(self):
        return {
            "title": "Root",
            "ideas": {
                "1":  {"title": "Right1", "ideas": {}},
                "2":  {"title": "Right2", "ideas": {}},
                "-1": {"title": "Left1",  "ideas": {}},
            },
        }

    def test_root_title(self):
        node = parse_mindmup_json(self._simple())
        self.assertEqual(node.text, "Root")

    def test_child_count(self):
        node = parse_mindmup_json(self._simple())
        self.assertEqual(len(node.children), 3)

    def test_key_numeric_sort(self):
        """Children must be ordered by float key: -1, 1, 2."""
        node = parse_mindmup_json(self._simple())
        self.assertEqual([c.text for c in node.children], ["Left1", "Right1", "Right2"])

    def test_position_assignment(self):
        node = parse_mindmup_json(self._simple())
        positions = {c.text: c.position for c in node.children}
        self.assertEqual(positions["Left1"],  "left")
        self.assertEqual(positions["Right1"], "right")
        self.assertEqual(positions["Right2"], "right")

    def test_nested_children_have_no_position(self):
        data = {
            "title": "Root",
            "ideas": {
                "1": {
                    "title": "Parent",
                    "ideas": {"1": {"title": "Child", "ideas": {}}},
                }
            },
        }
        node = parse_mindmup_json(data)
        grandchild = node.children[0].children[0]
        self.assertIsNone(grandchild.position)

    def test_empty_ideas(self):
        node = parse_mindmup_json({"title": "Solo", "ideas": {}})
        self.assertEqual(node.text, "Solo")
        self.assertEqual(node.children, [])

    def test_missing_ideas_key(self):
        node = parse_mindmup_json({"title": "Solo"})
        self.assertEqual(node.children, [])

    def test_fractional_keys_sorted(self):
        data = {
            "title": "Root",
            "ideas": {
                "1.5": {"title": "B", "ideas": {}},
                "0.5": {"title": "A", "ideas": {}},
            },
        }
        node = parse_mindmup_json(data)
        self.assertEqual([c.text for c in node.children], ["A", "B"])

    def test_sample_fixture(self):
        """Integration: parse the sample.mup fixture file structure."""
        data = json.loads((FIXTURES / "sample.mup").read_text())
        node = parse_mindmup_json(data)
        self.assertEqual(node.text, "My Project")
        texts = [c.text for c in node.children]
        # sorted order: -1 (Notes), 1 (Planning), 2 (Execution)
        self.assertEqual(texts, ["Notes", "Planning", "Execution"])
        planning = next(c for c in node.children if c.text == "Planning")
        self.assertEqual([c.text for c in planning.children], ["Research", "Design"])


# ---------------------------------------------------------------------------
# parse_mindmup_xml
# ---------------------------------------------------------------------------

class TestParseMindmupXml(unittest.TestCase):
    def _xml(self, src: str) -> Node:
        return parse_mindmup_xml(ET.fromstring(src))

    def test_map_root_with_node(self):
        src = '<map version="0.9.0"><node TEXT="Root"><node TEXT="A"/></node></map>'
        node = self._xml(src)
        self.assertEqual(node.text, "Root")
        self.assertEqual(len(node.children), 1)
        self.assertEqual(node.children[0].text, "A")

    def test_bare_node_root(self):
        src = '<node TEXT="Root"><node TEXT="Child"/></node>'
        node = self._xml(src)
        self.assertEqual(node.text, "Root")

    def test_lowercase_text_attr(self):
        src = '<map><node text="Root"><node text="Child"/></node></map>'
        node = self._xml(src)
        self.assertEqual(node.text, "Root")
        self.assertEqual(node.children[0].text, "Child")

    def test_auto_position_assignment(self):
        """Without POSITION attrs: first ceil(n/2) → right, rest → left."""
        src = (
            '<map><node TEXT="Root">'
            '<node TEXT="A"/><node TEXT="B"/><node TEXT="C"/>'
            '</node></map>'
        )
        node = self._xml(src)
        # n=3 → right_count=2 → A,B=right; C=left
        positions = [c.position for c in node.children]
        self.assertEqual(positions, ["right", "right", "left"])

    def test_explicit_position_preserved(self):
        src = (
            '<map version="1.0.1"><node TEXT="Root">'
            '<node TEXT="L" POSITION="left"/>'
            '<node TEXT="R" POSITION="right"/>'
            '</node></map>'
        )
        node = self._xml(src)
        self.assertEqual(node.children[0].position, "left")
        self.assertEqual(node.children[1].position, "right")

    def test_empty_map(self):
        src = '<map version="1.0.1"></map>'
        node = self._xml(src)
        self.assertEqual(node.text, "")
        self.assertEqual(node.children, [])

    def test_sample_legacy_fixture(self):
        src = (FIXTURES / "sample_legacy.mup").read_text()
        node = parse_mindmup_xml(ET.fromstring(src))
        self.assertEqual(node.text, "Legacy Map")
        self.assertEqual(len(node.children), 3)
        self.assertEqual(node.children[0].text, "Child One")
        self.assertEqual(node.children[0].children[0].text, "Grandchild")


# ---------------------------------------------------------------------------
# build_freemind
# ---------------------------------------------------------------------------

class TestBuildFreemind(unittest.TestCase):
    def _root(self):
        return Node(
            text="Root",
            children=[
                Node(text="Left",  position="left"),
                Node(text="Right", position="right", children=[
                    Node(text="Deep"),
                ]),
            ],
        )

    def _map_elem(self, node: Node) -> ET.Element:
        return build_freemind(node).getroot()

    def test_map_element_version(self):
        elem = self._map_elem(self._root())
        self.assertEqual(elem.tag, "map")
        self.assertEqual(elem.get("version"), "1.0.1")

    def test_root_node_text(self):
        elem = self._map_elem(self._root())
        root_node = elem.find("node")
        self.assertEqual(root_node.get("TEXT"), "Root")

    def test_child_position(self):
        elem = self._map_elem(self._root())
        root_node = elem.find("node")
        children = list(root_node)
        texts = {c.get("TEXT"): c.get("POSITION") for c in children}
        self.assertEqual(texts["Left"],  "left")
        self.assertEqual(texts["Right"], "right")

    def test_nested_node(self):
        elem = self._map_elem(self._root())
        deep = elem.find("./node/node[@TEXT='Right']/node")
        self.assertIsNotNone(deep)
        self.assertEqual(deep.get("TEXT"), "Deep")

    def test_no_position_on_deep_node(self):
        elem = self._map_elem(self._root())
        deep = elem.find("./node/node[@TEXT='Right']/node")
        self.assertIsNone(deep.get("POSITION"))

    def test_special_chars_escaped(self):
        node = Node(text="A & B < C > D")
        elem = self._map_elem(node)
        root_node = elem.find("node")
        self.assertEqual(root_node.get("TEXT"), "A & B < C > D")


# ---------------------------------------------------------------------------
# load_source (auto-detect)
# ---------------------------------------------------------------------------

class TestLoadSource(unittest.TestCase):
    def test_detects_json(self):
        node = load_source(FIXTURES / "sample.mup")
        self.assertEqual(node.text, "My Project")

    def test_detects_xml(self):
        node = load_source(FIXTURES / "sample_legacy.mup")
        self.assertEqual(node.text, "Legacy Map")

    def test_unknown_format_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".mup", mode="w", delete=False) as f:
            f.write("NOT_JSON_OR_XML content")
            path = Path(f.name)
        try:
            with self.assertRaises(ValueError):
                load_source(path)
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# convert_file (end-to-end)
# ---------------------------------------------------------------------------

class TestConvertFile(unittest.TestCase):
    def test_json_converts_to_mm(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = convert_file(FIXTURES / "sample.mup", Path(tmp))
            self.assertEqual(out.name, "sample.mm")
            tree = ET.parse(out)
            root = tree.getroot()
            self.assertEqual(root.tag, "map")
            root_node = root.find("node")
            self.assertEqual(root_node.get("TEXT"), "My Project")

    def test_xml_converts_to_mm(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = convert_file(FIXTURES / "sample_legacy.mup", Path(tmp))
            self.assertEqual(out.name, "sample_legacy.mm")
            tree = ET.parse(out)
            root_node = tree.getroot().find("node")
            self.assertEqual(root_node.get("TEXT"), "Legacy Map")

    def test_output_has_xml_declaration(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = convert_file(FIXTURES / "sample.mup", Path(tmp))
            content = out.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("<?xml"))

    def test_child_order_and_position_in_output(self):
        """Notes(left) < Planning(right) < Execution(right) — key sort -1,1,2."""
        with tempfile.TemporaryDirectory() as tmp:
            out = convert_file(FIXTURES / "sample.mup", Path(tmp))
            root_node = ET.parse(out).getroot().find("node")
            children = list(root_node)
            self.assertEqual(children[0].get("TEXT"), "Notes")
            self.assertEqual(children[0].get("POSITION"), "left")
            self.assertEqual(children[1].get("TEXT"), "Planning")
            self.assertEqual(children[1].get("POSITION"), "right")
            self.assertEqual(children[2].get("TEXT"), "Execution")
            self.assertEqual(children[2].get("POSITION"), "right")


if __name__ == "__main__":
    unittest.main()
