#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
test_fragment_join.py -- regression guard for join_fragments.

parakeet's transcribe_stream finalizes tokens in batches, and a single word
can split across two batches ("...the b" + "ank..."). The renderers used to
reassemble with `" ".join(f.strip() for f in fragments)`, which stripped the
token-boundary whitespace AND inserted a space, turning "bank" into "b ank" and
"integral" into "inte gral". join_fragments concatenates verbatim (preserving
each fragment's own leading-space convention) then collapses double spaces.

The cases use synthetic fragments that reproduce the split patterns observed in
real snapshots (no real transcript content). Run:
  uv run evals/test_fragment_join.py
"""
from __future__ import annotations

import re
from pathlib import Path

RECORDER = Path(__file__).resolve().parent.parent / "recorder"


def _load_join_fragments():
    src = RECORDER.read_text()
    m = re.search(
        r"\ndef join_fragments\(.*?\n(?=\ndef |\nclass |\n# ----)",
        src, re.S,
    )
    if not m:
        raise AssertionError("join_fragments not found in recorder source")
    ns: dict = {"re": re}
    exec(m.group(0), ns)
    return ns["join_fragments"]


def main() -> int:
    join = _load_join_fragments()
    failures = []

    def check(label, frags, want):
        got = join(frags)
        if got != want:
            failures.append(f"{label}: got {got!r}, want {want!r}")

    # The core bug: a word split across two finalized batches. The fragments
    # carry their own spacing (continuation has NO leading space), so verbatim
    # concat must re-form the word with no inserted space.
    check("split word 'banana'",
          [" we bought a ba", "nana from the store"],
          "we bought a banana from the store")
    check("split word 'integral'",
          [" make a new inte", "gral and another integration"],
          "make a new integral and another integration")
    check("split word mid-sentence with punctuation",
          [". Then the wid", "get loads. Um"],
          ". Then the widget loads. Um")
    check("split proper-ish word",
          [" wait for the sig", "nal, then go. Okay."],
          "wait for the signal, then go. Okay.")
    check("split word 'automation'",
          [" check the autom", "ation. Um"],
          "check the automation. Um")

    # New-word fragments DO carry a leading space; concat must keep exactly one.
    check("normal word boundaries",
          [" there is a sound", " only the", " time here."],
          "there is a sound only the time here.")

    # Sentence boundaries must NOT glue: parakeet puts the space at the start of
    # the next word, so concat preserves the gap after punctuation.
    check("sentence boundary keeps space",
          ["that is funny. Um", " it is actually fine"],
          "that is funny. Um it is actually fine")

    # ASR double spaces collapse to one.
    check("double space collapses",
          ["the  um  yes, that is the way it works"],
          "the um yes, that is the way it works")

    # Leading/trailing whitespace on the whole paragraph is trimmed.
    check("edges trimmed",
          ["  leading", " and trailing  "],
          "leading and trailing")

    # A polished block (already-normalized prose) passes through unharmed.
    check("polished block untouched",
          ["This is a clean rewritten sentence."],
          "This is a clean rewritten sentence.")

    if failures:
        print("FAIL:")
        for f in failures:
            print("  " + f)
        return 1
    print(f"PASS: fragment join (9 cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
