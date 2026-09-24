"""Shiki alignment coverage.

Runs ``scripts/shiki_coverage.py`` (needs Node + ``scripts/shiki/node_modules``)
and asserts SyntaxFont still colors at least a floor fraction of the characters
Shiki colors. Skips cleanly when Shiki is not installed so the suite stays
runnable offline; CI installs it explicitly.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

spec = importlib.util.spec_from_file_location(
    "shiki_coverage", os.path.join(ROOT, "scripts", "shiki_coverage.py")
)
shiki_coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shiki_coverage)

# floor for the "any" metric (SyntaxFont colors the char at all) on the
# real-world coverage corpus. Keep a little below the current value so small
# regressions are caught without being brittle.
MIN_ANY_COVERAGE = 70.0


@pytest.fixture(scope="module")
def coverage():
    if not shiki_coverage.shiki_available():
        pytest.skip("shiki not installed (cd scripts/shiki && npm install)")
    return shiki_coverage.measure()


def test_shiki_overall_coverage(coverage):
    overall = coverage["__overall__"]
    pct = 100.0 * overall["any_hit"] / overall["total"]
    assert pct >= MIN_ANY_COVERAGE, (
        f"Shiki coverage dropped to {pct:.1f}% (min {MIN_ANY_COVERAGE}%)"
    )


@pytest.mark.parametrize("lang", sorted(shiki_coverage.PROBES))
def test_shiki_per_language_coverage(lang, coverage):
    row = coverage[lang]
    if not row["total"]:
        pytest.skip("no probes")
    pct = 100.0 * row["any_hit"] / row["total"]
    # a per-language floor, generous enough for the languages with the largest
    # known gaps (SQL keywords, markdown prose)
    assert pct >= 30.0, f"{lang}: shiki coverage {pct:.1f}%"

    # report what is still missed, as a comment in the failure for triage
    missed = row["missed"]
    if missed:
        sample = ", ".join(f"{m['char']!r}({m['want']})" for m in missed[:10])
        print(f"{lang}: missed {len(missed)} chars, e.g. {sample}")
