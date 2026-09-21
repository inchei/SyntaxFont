"""syntaxfont — build a font with built-in syntax highlighting."""

from .builder import build_highlight_font
from .schema import Language, Theme, parse_language, parse_theme

__all__ = ["build_highlight_font", "Language", "Theme", "parse_language", "parse_theme"]
__version__ = "0.1.0"
