"""TrueType collections: list faces and build from a selected face."""

from __future__ import annotations

import os
import struct

from fontTools.ttLib import TTFont

from syntaxfont.builder import build_highlight_font
from syntaxfont.webapp import ttc_faces

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_FONT = os.path.join(ROOT, "assets", "JetBrainsMono-Regular.ttf")


def make_ttc(blobs: list[bytes]) -> bytes:
    header_len = 12 + 4 * len(blobs)
    parts, offset = [], header_len
    for blob in blobs:
        (num_tables,) = struct.unpack(">H", blob[4:6])
        shifted = bytearray(blob)
        for i in range(num_tables):
            pos = 12 + 16 * i + 8
            (table_offset,) = struct.unpack(">L", blob[pos : pos + 4])
            struct.pack_into(">L", shifted, pos, table_offset + offset)
        parts.append(bytes(shifted))
        offset += len(blob)
    face_offsets = [header_len + sum(len(p) for p in parts[:i]) for i in range(len(blobs))]
    return (
        struct.pack(">4sLL", b"ttcf", 0x10000, len(blobs))
        + b"".join(struct.pack(">L", o) for o in face_offsets)
        + b"".join(parts)
    )


def _base_blob() -> bytes:
    with open(BASE_FONT, "rb") as fh:
        return fh.read()


def test_plain_font_lists_single_face():
    faces = ttc_faces(_base_blob())
    assert len(faces) == 1
    assert faces[0] == {"index": 0, "family": "JetBrains Mono", "style": "Regular"}


def test_ttc_faces_listed(tmp_path):
    ttc = make_ttc([_base_blob(), _base_blob()])
    faces = ttc_faces(ttc)
    assert [f["index"] for f in faces] == [0, 1]
    assert all(f["family"] == "JetBrains Mono" for f in faces)


def test_build_second_face(tmp_path, languages, theme):
    ttc_path = tmp_path / "two.ttc"
    with open(ttc_path, "wb") as fh:
        fh.write(make_ttc([_base_blob(), _base_blob()]))
    out = tmp_path / "hl.ttf"
    build_highlight_font(
        str(ttc_path), languages, theme, str(out), flavor=None, font_number=1
    )
    font = TTFont(str(out))
    assert font["name"].getDebugName(1) == "JetBrains Mono Syntax"
    assert "COLR" in font and "GSUB" in font


def test_cli_default_family_from_face(tmp_path):
    from syntaxfont.cli import default_family

    ttc_path = tmp_path / "two.ttc"
    with open(ttc_path, "wb") as fh:
        fh.write(make_ttc([_base_blob(), _base_blob()]))
    assert default_family(str(ttc_path), 1) == "JetBrains Mono Syntax"
