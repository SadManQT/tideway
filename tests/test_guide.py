"""Regression checks for Tideway's public handbook page."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def _without_comments(source):
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", source)


def _matching_bracket(source, opening):
    pairs = {"[": "]", "{": "}", "(": ")"}
    closing = pairs[source[opening]]
    depth = 0
    quote = None
    escaped = False
    for index in range(opening, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "'\"`":
            quote = char
        elif char == source[opening]:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


def _array_item_count(body):
    if not body.strip():
        return 0
    depth = 0
    items = 1
    quote = None
    escaped = False
    for char in body:
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "'\"`":
            quote = char
        elif char in "[{(":
            depth += 1
        elif char in "]})":
            depth -= 1
        elif char == "," and depth == 0:
            items += 1
    return items


def _array_lengths(source):
    """Return lengths for simple JavaScript array constants."""
    lengths = {}
    declaration = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*\[")
    for match in declaration.finditer(source):
        end = _matching_bracket(source, match.end() - 1)
        if end is not None:
            lengths[match.group(1)] = _array_item_count(source[match.end():end])
    return lengths


def _strip_outer_parentheses(expression):
    expression = expression.strip()
    while expression.startswith("(") and expression.endswith(")"):
        end = _matching_bracket(expression, 0)
        if end != len(expression) - 1:
            break
        expression = expression[1:-1].strip()
    return expression


def _viva_question_count_at_least_thousand(source):
    """Evaluate deterministic count constants/products without executing JavaScript."""
    source = _without_comments(source)
    arrays = _array_lengths(source)
    assignments = re.compile(
        r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*([^;\n]+)"
    )
    declarations = assignments.findall(source)
    known = {}

    for name, expression in declarations:
        expression = _strip_outer_parentheses(expression)
        literal = re.fullmatch(r"\d+", expression)
        if literal:
            known[name] = int(literal.group())
        else:
            length = re.fullmatch(r"([A-Za-z_$][\w$]*)\.length", expression)
            if length and length.group(1) in arrays:
                known[name] = arrays[length.group(1)]

    def evaluate(expression):
        factors = [_strip_outer_parentheses(part) for part in expression.split("*")]
        if len(factors) < 2:
            literal = re.fullmatch(r"\d+", factors[0])
            return int(literal.group()) if literal else known.get(factors[0])
        values = []
        for factor in factors:
            if re.fullmatch(r"\d+", factor):
                values.append(int(factor))
            elif factor in known:
                values.append(known[factor])
            else:
                length = re.fullmatch(r"([A-Za-z_$][\w$]*)\.length", factor)
                if not length or length.group(1) not in arrays:
                    return None
                values.append(arrays[length.group(1)])
        result = 1
        for value in values:
            result *= value
        return result

    for name, expression in declarations:
        value = evaluate(expression)
        context = f"{name} {expression}"
        if value is not None and value >= 1000 and re.search(
            r"(?i)viva|question|categor(?:y|ies)|angle(?:s)?", context
        ):
            return True

    # Also accept a clearly labelled literal or numeric product used directly by
    # the generator, even when it is not assigned to a const/let/var declaration.
    for line in source.splitlines():
        if not re.search(r"(?i)viva|question|categor(?:y|ies)|angle(?:s)?", line):
            continue
        for literal in re.findall(r"\b\d{4,}\b", line):
            if int(literal) >= 1000:
                return True
        for left, right in re.findall(r"\b(\d+)\s*\*\s*(\d+)\b", line):
            if int(left) * int(right) >= 1000:
                return True
    return False


class GuidePageTests(unittest.TestCase):
    def _read(self, name):
        path = WEB / name
        self.assertTrue(path.is_file(), f"Expected public guide asset: {path}")
        return path.read_text(encoding="utf-8")

    def test_public_guide_assets_exist(self):
        for name in ("guide.html", "guide.css", "guide.js"):
            with self.subTest(name=name):
                self.assertTrue((WEB / name).is_file())

    def test_server_exposes_guide_assets(self):
        from tideway.server import STATIC

        self.assertEqual(STATIC["/guide"], "guide.html")
        self.assertEqual(STATIC["/guide.html"], "guide.html")
        self.assertEqual(STATIC["/guide.css"], "guide.css")
        self.assertEqual(STATIC["/guide.js"], "guide.js")

    def test_guide_markup_has_sections_assets_disclaimer_and_setup(self):
        html = self._read("guide.html")
        for anchor in ("overview", "problems", "response", "features", "setup", "viva"):
            with self.subTest(anchor=anchor):
                self.assertRegex(html, rf'href\s*=\s*["\']#{anchor}["\']')
        self.assertRegex(html, r'<link\b[^>]*\bhref\s*=\s*["\'][^"\']*guide\.css(?:[?#][^"\']*)?["\']')
        self.assertRegex(html, r'<script\b[^>]*\bsrc\s*=\s*["\'][^"\']*guide\.js(?:[?#][^"\']*)?["\']')
        normalized = re.sub(r"\s+", " ", html).lower()
        self.assertIn("synthetic sandbox", normalized)
        self.assertIn("no real money", normalized)
        self.assertIn("python3 run.py", html)

    def test_guide_javascript_has_viva_generator_and_thousand_questions(self):
        script = self._read("guide.js")
        self.assertRegex(
            script,
            re.compile(
                r"(?i)\b(?:generate|build|create|make)[A-Za-z0-9_$]*viva[A-Za-z0-9_$]*\b"
                r"|\bviva[A-Za-z0-9_$]*(?:generator|questions?)\b"
            ),
        )
        self.assertTrue(
            _viva_question_count_at_least_thousand(script),
            "guide.js must deterministically generate/prove at least 1,000 Viva questions",
        )


if __name__ == "__main__":
    unittest.main()
