"""Shared paths and a HarfBuzz shaping helper for the test suite."""

from __future__ import annotations

import os

import uharfbuzz as hb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_FONT = os.path.join(ROOT, "assets", "JetBrainsMono-Regular.ttf")
JS_YAML = open(os.path.join(ROOT, "languages", "js.yaml")).read()
DEFAULT_YAML = open(os.path.join(ROOT, "themes", "default.yaml")).read()


def shape_font(path: str, text: str, features: dict | None = None) -> list[str]:
    """Shape ``text`` with the font at ``path`` and return the glyph names."""
    font = hb.Font(hb.Face(hb.Blob.from_file_path(path)))
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, features if features is not None else {"calt": True})
    return [font.glyph_to_string(i.codepoint) for i in buf.glyph_infos]
