#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "jiwer>=3.0",
#   "pyannote.metrics>=3.2",
# ]
# ///
"""
run_eval.py -- recorder eval harness

Measures:
  - WER  : word error rate vs reference transcript (where available)
  - DER  : diarization error rate vs reference RTTM (where available)
  - Live/offline gap : streaming vs full-attention on the same clip

Usage:
  uv run evals/run_eval.py [--corpus path] [--clip ID] [--skip-live]
  uv run evals/run_eval.py --design-only     # print A/B and hallucination designs

Known limitations (see evals/README.md):
  - WER alignment: jiwer normalizes by lowercasing + punctuation strip.
    Contractions (it's vs its), British spelling, and ASR-style spacing
    around numbers can inflate WER by 2-5 points vs human-scored transcripts.
  - DER: pyannote.metrics collar=0.25s (NIST standard).
    Does NOT handle overlapping speech regions correctly by default;
    overlap region DER is counted against both speakers simultaneously.
  - The `recorder` CLI must be on PATH and accept:
      recorder --from-file <path>      (live/streaming mode)
      recorder redo <path>             (offline full-attention mode)
  - Both modes are expected to write JSON to stdout with key "transcript".
    If your CLI writes differently, edit `run_recorder_live` / `run_recorder_offline`.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Standard Python logging. Default level INFO; set EVAL_LOG=DEBUG for verbose.
# Format: short timestamp + level + message; goes to stderr so stdout stays
# usable for piping the report.
logging.basicConfig(
    level=os.environ.get("EVAL_LOG", "INFO"),
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
log = logging.getLogger("eval")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = Path(__file__).resolve().parent
CORPUS_DIR = Path.home() / "recordings" / "test-corpus"
CORPUS_TOML = EVALS_DIR / "corpus.toml"

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Clip:
    id: str
    path: Path
    duration_s: Optional[float]
    speakers: int
    ref_transcript: Optional[Path]   # .txt, one sentence per line
    ref_rttm: Optional[Path]         # RTTM speaker segmentation
    has_ground_truth: bool = False
    notes: str = ""

    def __post_init__(self):
        self.has_ground_truth = (
            self.ref_transcript is not None or self.ref_rttm is not None
        )


@dataclass
class EvalResult:
    clip_id: str
    duration_s: Optional[float]
    live_transcript: Optional[str] = None
    offline_transcript: Optional[str] = None
    live_wer: Optional[float] = None
    offline_wer: Optional[float] = None
    offline_gain: Optional[float] = None   # live_wer - offline_wer (positive = offline better)
    # live_vs_offline_wer: WER of live transcript using THIS pass's offline
    # output as reference (not the frozen ref). Eliminates the "frozen ref
    # is stale relative to current settings" problem A1 from /flaws.
    live_vs_offline_wer: Optional[float] = None
    der: Optional[float] = None
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Corpus loader (reads corpus.toml if present, else falls back to defaults)
# ---------------------------------------------------------------------------

DEFAULT_CORPUS: list[dict] = [
    {
        "id": "L1",
        "path": "librispeech/1272-128104-0000.flac",
        "duration_s": 14.0,
        "speakers": 1,
        "ref_transcript": "librispeech/1272-128104.trans.txt",
        "ref_rttm": None,
        "notes": "LibriSpeech dev-clean, clean male baseline",
    },
    {
        "id": "L2",
        "path": "librispeech/1272-128104-0001.flac",
        "duration_s": 9.0,
        "speakers": 1,
        "ref_transcript": "librispeech/1272-128104.trans.txt",
        "ref_rttm": None,
        "notes": "LibriSpeech dev-clean, second utterance",
    },
    {
        "id": "S1",
        "path": "swc/Niels_Bohr.flac",
        "duration_s": 240.0,
        "speakers": 1,
        "ref_transcript": "swc/Niels_Bohr_ref.txt",
        "ref_rttm": None,
        "notes": "Spoken Wikipedia, proper-noun-heavy (physics)",
    },
    {
        "id": "S2",
        "path": "swc/Alan_Turing.flac",
        "duration_s": 300.0,
        "speakers": 1,
        "ref_transcript": "swc/Alan_Turing_ref.txt",
        "ref_rttm": None,
        "notes": "Spoken Wikipedia, proper-noun-heavy (CS history)",
    },
    {
        "id": "A1",
        "path": "ami/ES2002a.Headset-0.flac",
        "duration_s": 1800.0,
        "speakers": 4,
        "ref_transcript": None,
        "ref_rttm": "ami/ES2002a.rttm",
        "notes": "AMI ES2002a headset, 4-speaker product design meeting",
    },
    {
        "id": "A2",
        "path": "ami/IS1009b.Headset-0.flac",
        "duration_s": 1800.0,
        "speakers": 4,
        "ref_transcript": None,
        "ref_rttm": "ami/IS1009b.rttm",
        "notes": "AMI IS1009b headset, 4-speaker project meeting",
    },
    {
        "id": "V1",
        "path": "voxconverse/aepyx.wav",
        "duration_s": 240.0,
        "speakers": 3,
        "ref_transcript": None,
        "ref_rttm": "voxconverse/aepyx.rttm",
        "notes": "VoxConverse test clip, overlap-heavy in-the-wild",
    },
    {
        "id": "V2",
        "path": "voxconverse/bfkdi.wav",
        "duration_s": 240.0,
        "speakers": 2,
        "ref_transcript": None,
        "ref_rttm": "voxconverse/bfkdi.rttm",
        "notes": "VoxConverse test clip, 2-speaker in-the-wild",
    },
    {
        "id": "P1",
        "path": "librivox/sherlock_01_3min.flac",
        "duration_s": 180.0,
        "speakers": 1,
        "ref_transcript": None,
        "ref_rttm": None,
        "notes": "LibriVox Sherlock Holmes ch.1 (trimmed 3 min), no ground truth",
    },
]


def load_corpus(clip_filter: Optional[str] = None,
                corpus_toml: Optional[Path] = None,
                corpus_dir: Optional[Path] = None) -> list[Clip]:
    """Load clips. Path resolution:
      - if `corpus_toml` is given (or default exists), read its [[clips]].
      - otherwise use DEFAULT_CORPUS.
      - relative paths in entries are resolved against `corpus_dir`
        (or CORPUS_DIR by default).
    Each entry's `path` MAY be absolute (used by ad-hoc evals).
    """
    base = corpus_dir or CORPUS_DIR
    raw: list[dict] = []
    toml_path = corpus_toml or CORPUS_TOML
    if toml_path.exists():
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        raw = data.get("clips", [])
    if not raw:
        raw = DEFAULT_CORPUS

    def _resolve(p: Optional[str]) -> Optional[Path]:
        """Tilde-expand FIRST, then check absolute, then resolve vs base."""
        if not p:
            return None
        x = Path(p).expanduser()
        if x.is_absolute():
            return x
        return base / x

    clips = []
    for entry in raw:
        path = _resolve(entry["path"])
        ref_transcript = _resolve(entry.get("ref_transcript"))
        ref_rttm = _resolve(entry.get("ref_rttm"))
        clip = Clip(
            id=entry["id"],
            path=path,
            duration_s=entry.get("duration_s"),
            speakers=entry.get("speakers", 1),
            ref_transcript=ref_transcript,
            ref_rttm=ref_rttm,
            notes=entry.get("notes", ""),
        )
        if clip_filter and clip.id != clip_filter:
            continue
        clips.append(clip)
    return clips


# ---------------------------------------------------------------------------
# recorder CLI invocation
# ---------------------------------------------------------------------------

def _read_transcript_artifact(out_dir: Path, name: str, kind: str) -> Optional[str]:
    """Recorder writes <name>.txt (live) and <name>.offline.txt (offline).

    Both have a `# ...` banner header AND (live mode) a `# ended:` footer.
    Strip both, plus 5-min markers like `[00:05:00]`. Returns None on miss
    or empty body.
    """
    candidates = {
        "live": out_dir / f"{name}.txt",
        "offline": out_dir / f"{name}.offline.txt",
    }
    p = candidates.get(kind)
    if not p or not p.exists():
        return None
    text = p.read_text(encoding="utf-8")
    body_lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("#"):
            continue                          # banner header / footer
        if re.fullmatch(r"\[\d{2}:\d{2}:\d{2}\][\s★]*", s):
            continue                          # 5-min markers + user marks
        body_lines.append(ln)
    return "\n".join(body_lines).strip() or None


def run_recorder_live(audio_path: Path, timeout: int = 1800) -> Optional[str]:
    """Invoke recorder in streaming/live mode on a file.

    Recorder writes <name>.txt; we read it back. Use --no-offline-pass
    so we measure the LIVE path only (offline is measured separately).
    """
    name = f"eval-live-{audio_path.stem}"
    out_dir = Path(tempfile.mkdtemp(prefix="recorder-eval-"))
    try:
        env = {**os.environ, "MEETING_DIR": str(out_dir), "MEETING_PORT": "0"}
        result = subprocess.run(
            ["recorder", "--no-browser", "--no-offline-pass",
             "--from-file", str(audio_path), name],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
        if result.returncode not in (0, 255):
            log.warning("recorder live rc=%d: %s",
                        result.returncode, result.stderr[-200:].strip())
        artifact = _read_transcript_artifact(out_dir, name, "live")
        log.debug("  live artifact dir=%s files=%s",
                  out_dir, [p.name for p in out_dir.iterdir()])
        return artifact
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning("recorder live failed: %s", e)
        return None


def run_recorder_offline(audio_path: Path, timeout: int = 1800) -> Optional[str]:
    """Invoke recorder offline mode via the `redo` subcommand.

    `redo --force` is needed because we run repeatedly on the same FLAC.
    Recorder writes <stem>.offline.txt next to the FLAC.
    """
    try:
        result = subprocess.run(
            ["recorder", "redo", str(audio_path), "--force"],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            log.warning("recorder redo rc=%d: %s",
                        result.returncode, result.stderr[-200:].strip())
            return None
        artifact = _read_transcript_artifact(audio_path.parent, audio_path.stem, "offline")
        log.debug("  offline artifact dir=%s",
                  list(audio_path.parent.glob(f"{audio_path.stem}.offline.*")))
        return artifact
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning("recorder redo failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# WER computation
# ---------------------------------------------------------------------------

def load_reference_transcript(path: Path, clip_id: str,
                              audio_path: Optional[Path] = None) -> Optional[str]:
    """
    Load reference text matching the audio clip.

    LibriSpeech .trans.txt format: "1272-128104-0000 MISTER QUILTER ..."
    If audio_path is provided and looks like a LibriSpeech utterance ID
    (e.g. 1272-128104-0000.flac), match the line with that prefix.
    Otherwise concatenate all lines.
    """
    if not path.exists():
        return None
    text = path.read_text()
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return None

    if audio_path is not None:
        utt_id = audio_path.stem  # e.g. "1272-128104-0000"
        for ln in lines:
            parts = ln.split(None, 1)
            if len(parts) == 2 and parts[0] == utt_id:
                return parts[1]

    # Fallback: concatenate all lines (strip leading utterance IDs if present)
    out = []
    for ln in lines:
        parts = ln.split(None, 1)
        if len(parts) == 2 and "-" in parts[0]:
            out.append(parts[1])
        else:
            out.append(ln)
    return " ".join(out)


def normalize_for_wer(text: str) -> str:
    """
    Minimal normalization that matches jiwer's default transforms.
    Pitfall documented: this can over-normalize (e.g. "it's" -> "its" may
    differ from ASR output). Document but do not suppress the delta.
    """
    import jiwer

    transforms = jiwer.Compose([
        jiwer.ToLowerCase(),
        jiwer.RemovePunctuation(),
        jiwer.RemoveMultipleSpaces(),
        jiwer.Strip(),
        jiwer.RemoveEmptyStrings(),
    ])
    return transforms([text])[0]


def compute_wer(hypothesis: str, reference: str) -> Optional[float]:
    """Returns WER in [0, 1+]. Returns None if either string is empty.

    jiwer 4.x removed `compute_measures`; use `wer()` (returns float) or
    `process_words()` (richer object) — we only need the scalar.
    """
    try:
        import jiwer
    except ImportError:
        log.warning("jiwer not installed; WER=None")
        return None

    try:
        hyp = normalize_for_wer(hypothesis)
        ref = normalize_for_wer(reference)
    except Exception as e:
        log.warning("normalize failed: %s", e)
        return None

    if not hyp or not ref:
        log.debug("compute_wer: empty after normalize hyp=%r ref=%r", hyp, ref)
        return None

    try:
        return jiwer.wer(ref, hyp)
    except Exception as e:
        log.warning("jiwer.wer failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# DER computation
# ---------------------------------------------------------------------------

def parse_rttm(path: Path) -> list[tuple[float, float, str]]:
    """
    Parse RTTM file into list of (start_s, duration_s, speaker_label).
    RTTM format: SPEAKER <file> <chn> <start> <dur> <NA> <NA> <speaker> <NA> <NA>
    """
    segments = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        parts = line.split()
        if len(parts) < 8 or parts[0] != "SPEAKER":
            continue
        try:
            start = float(parts[3])
            duration = float(parts[4])
            speaker = parts[7]
            segments.append((start, duration, speaker))
        except (ValueError, IndexError):
            continue
    return segments


def write_temp_rttm(segments: list[tuple[float, float, str]], file_id: str = "eval") -> Path:
    """Write segments to a temp RTTM file for pyannote.metrics."""
    tmp = Path(tempfile.mktemp(suffix=".rttm"))
    with open(tmp, "w") as f:
        for start, dur, spk in segments:
            f.write(f"SPEAKER {file_id} 1 {start:.3f} {dur:.3f} <NA> <NA> {spk} <NA> <NA>\n")
    return tmp


def transcript_to_rttm_segments(
    transcript_json: str,
    default_speaker: str = "SPEAKER_00",
) -> list[tuple[float, float, str]]:
    """
    Convert recorder's JSON output (expected to contain timestamped words or segments)
    into RTTM-format segments for DER computation.

    Expected transcript JSON shape (recorder output):
      {
        "segments": [
          {"start": 0.0, "end": 2.3, "speaker": "SPEAKER_00", "text": "..."},
          ...
        ]
      }

    If the output lacks speaker or timing info, DER cannot be computed.
    """
    try:
        data = json.loads(transcript_json)
    except (json.JSONDecodeError, TypeError):
        return []

    segments = data.get("segments", [])
    result = []
    for seg in segments:
        start = seg.get("start")
        end = seg.get("end")
        speaker = seg.get("speaker", default_speaker)
        if start is None or end is None:
            continue
        dur = end - start
        if dur <= 0:
            continue
        result.append((float(start), float(dur), speaker))
    return result


def compute_der(
    hypothesis_segments: list[tuple[float, float, str]],
    reference_rttm: Path,
    collar: float = 0.25,
) -> Optional[float]:
    """
    Compute Diarization Error Rate using pyannote.metrics.
    collar: time in seconds around segment boundaries that is excluded from scoring (NIST standard: 0.25s).
    Returns DER in [0, 1+]. Returns None if pyannote.metrics is unavailable or input is empty.

    Limitation: does not handle overlapping speech; both speakers' overlap region
    is counted against the hypothesis simultaneously.
    """
    try:
        from pyannote.core import Annotation, Segment
        from pyannote.metrics.diarization import DiarizationErrorRate
    except ImportError:
        return None

    if not reference_rttm.exists() or not hypothesis_segments:
        return None

    ref_segs = parse_rttm(reference_rttm)
    if not ref_segs:
        return None

    reference = Annotation()
    for start, dur, spk in ref_segs:
        reference[Segment(start, start + dur)] = spk

    hypothesis = Annotation()
    for start, dur, spk in hypothesis_segments:
        hypothesis[Segment(start, start + dur)] = spk

    metric = DiarizationErrorRate(collar=collar, skip_overlap=False)
    return float(metric(reference, hypothesis))


# ---------------------------------------------------------------------------
# Per-clip evaluation
# ---------------------------------------------------------------------------

def eval_clip(clip: Clip, skip_live: bool = False) -> EvalResult:
    result = EvalResult(clip_id=clip.id, duration_s=clip.duration_s)

    if not clip.path.exists():
        result.errors.append(f"audio file not found: {clip.path}")
        return result

    # Load reference transcript (needed for WER)
    ref_text: Optional[str] = None
    if clip.ref_transcript and clip.ref_transcript.exists():
        ref_text = load_reference_transcript(
            clip.ref_transcript, clip.id, audio_path=clip.path,
        )

    # --- offline mode ---
    log.info("[%s] offline mode", clip.id)
    log.debug("  audio=%s ref=%s ref_text_len=%d",
              clip.path, clip.ref_transcript, len(ref_text) if ref_text else 0)
    offline_raw = run_recorder_offline(clip.path)
    log.debug("  offline_raw len=%d", len(offline_raw) if offline_raw else 0)
    if offline_raw:
        log.debug("  offline_raw head=%r", offline_raw[:120])
    if offline_raw is not None:
        try:
            offline_data = json.loads(offline_raw)
            result.offline_transcript = offline_data.get("transcript") or offline_data.get("text") or offline_raw
        except json.JSONDecodeError:
            result.offline_transcript = offline_raw

        if ref_text and result.offline_transcript:
            result.offline_wer = compute_wer(result.offline_transcript, ref_text)
            log.debug("  offline_wer=%s ref_head=%r hyp_head=%r",
                      result.offline_wer, ref_text[:80], result.offline_transcript[:80])

        # DER for offline mode
        if clip.ref_rttm:
            offline_segments = transcript_to_rttm_segments(offline_raw)
            if offline_segments:
                result.der = compute_der(offline_segments, clip.ref_rttm)
            else:
                result.errors.append("offline output lacks segment timing; DER skipped")
    else:
        result.errors.append("offline mode returned no output (is `recorder redo` on PATH?)")

    # --- live/streaming mode ---
    if not skip_live:
        log.info("[%s] live mode", clip.id)
        live_raw = run_recorder_live(clip.path)
        log.debug("  live_raw len=%d", len(live_raw) if live_raw else 0)
        if live_raw:
            log.debug("  live_raw head=%r", live_raw[:120])
        if live_raw is not None:
            try:
                live_data = json.loads(live_raw)
                result.live_transcript = live_data.get("transcript") or live_data.get("text") or live_raw
            except json.JSONDecodeError:
                result.live_transcript = live_raw

            if ref_text and result.live_transcript:
                result.live_wer = compute_wer(result.live_transcript, ref_text)
            # Same-run live-vs-offline: more honest streaming-cost metric
            # because both transcripts came from the same model invocation
            # boundary. Frozen ref can drift if model defaults change.
            if result.offline_transcript and result.live_transcript:
                result.live_vs_offline_wer = compute_wer(
                    result.live_transcript, result.offline_transcript,
                )
        else:
            result.errors.append("live mode returned no output (is `recorder --from-file` on PATH?)")

    # Compute offline gain
    if result.live_wer is not None and result.offline_wer is not None:
        result.offline_gain = result.live_wer - result.offline_wer

    return result


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def format_pct(v: Optional[float], width: int = 7) -> str:
    if v is None:
        return " " * (width - 1) + "-"
    return f"{v * 100:>{width}.1f}%"


def write_report(results: list[EvalResult], output_path: Path) -> None:
    today = datetime.date.today().isoformat()
    lines = [
        f"# recorder eval results -- {today}",
        "",
        "WER: jiwer, lowercase+no-punct normalization. Lower is better.",
        "DER: pyannote.metrics, collar=0.25s, overlap counted. Lower is better.",
        "Offline gain: live WER minus offline WER. Positive means offline is better.",
        "",
        "## Results",
        "",
        "| Clip | Duration | Live WER | Offline WER | Offline gain | DER | Notes |",
        "|------|----------|----------|-------------|--------------|-----|-------|",
    ]
    for r in results:
        dur = f"{r.duration_s:.0f}s" if r.duration_s else "-"
        errors = "; ".join(r.errors) if r.errors else ""
        lines.append(
            f"| {r.clip_id} "
            f"| {dur} "
            f"| {format_pct(r.live_wer)} "
            f"| {format_pct(r.offline_wer)} "
            f"| {format_pct(r.offline_gain)} "
            f"| {format_pct(r.der)} "
            f"| {errors} |"
        )

    lines += [
        "",
        "## Known alignment pitfalls",
        "",
        "- Contractions: 'it\\'s' vs 'its' are treated as different words by jiwer.",
        "- Number formatting: '1913' vs 'nineteen thirteen' inflates WER by ~2 words.",
        "- ASR may omit filler words ('um', 'uh'); reference transcripts may include them.",
        "- LibriSpeech refs are all-caps; normalization lowercases both sides.",
        "- DER collar (0.25s) is generous; pyannote default is 0s. NIST benchmark uses 0.25s.",
        "",
        "## Clips missing ground truth",
        "",
    ]
    for r in results:
        if r.live_wer is None and r.offline_wer is None and r.der is None and not r.errors:
            lines.append(f"- {r.clip_id}: no reference transcript or RTTM available")

    output_path.write_text("\n".join(lines) + "\n")
    print(f"Report written: {output_path}")


# ---------------------------------------------------------------------------
# A/B polish design (printed, not run)
# ---------------------------------------------------------------------------

POLISH_AB_DESIGN = """
## A/B polish eval design (not run by this script)

Goal: determine whether gemma4:e2b polish (SUB/INS_AFTER/CAP edit script)
      net-improves or net-degrades WER vs raw parakeet output.

Procedure:
  1. Take each clip with a reference transcript (L1, L2, S1, S2).
  2. Run recorder in offline mode with --no-polish flag to get raw ASR output (A).
  3. Run recorder in offline mode with polish enabled (default) to get polished output (B).
  4. Compute WER(A, ref) and WER(B, ref) using the same jiwer normalization.
  5. delta_WER = WER(A) - WER(B)  (positive = polish helped)

Key risks:
  - Polish may improve capitalization/punctuation but those are stripped by jiwer;
    so WER will UNDERCOUNT polish benefit. Consider a case-sensitive WER variant.
  - If gemma4:e2b hallucinates a substitution (e.g. "Cross Camp" -> "Chris Kemp"),
    it will INCREASE WER even if the output reads more naturally.
  - Measure separately: SUB edits vs INS_AFTER edits vs CAP edits.
    A SUB that replaces a correct word with a wrong one is the adversarial case.

Suggested metric addition:
  - Entity preservation rate: what fraction of proper nouns in the reference
    appear verbatim in hypothesis? Tracks the "Cross Camp / Chris Kemp" class.
    Implementation: extract NNP tokens from ref via spacy; check membership in hyp.

CLI flags needed (add to recorder if absent):
  recorder redo <clip> --json --no-polish   # raw parakeet only
  recorder redo <clip> --json               # with polish (default)
"""

# ---------------------------------------------------------------------------
# Hallucination detection design (printed, not run)
# ---------------------------------------------------------------------------

HALLUCINATION_DESIGN = """
## Summary hallucination check design (not run by this script)

Goal: flag proper nouns and dates in the gemma4:latest summary that do not
      appear in the source transcript.

Procedure:
  1. Obtain source transcript T (the polished offline transcript).
  2. Obtain summary S (recorder's gemma4 summary output).
  3. Extract "anchored entities" from S:
       a. All tokens matching /[A-Z][a-z]+/ (capitalized words not at sentence start).
       b. All tokens matching /\\b(19|20)\\d{2}\\b/ (years).
       c. All tokens matching /\\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\.?\\s+\\d{1,2}/i (dates).
  4. For each anchored entity E:
       check = any(E.lower() in segment.lower() for segment in T.split(". "))
       if not check: flag as POTENTIAL HALLUCINATION
  5. Output: list of flagged entities with the summary sentence they appear in.

False positive classes to expect:
  - Anaphora: summary says "Einstein" but transcript only has "he" referring to Einstein.
    The entity is inferred, not hallucinated. Flag anyway; human review is fast.
  - Paraphrases: transcript says "the nineteen-thirties"; summary says "1930s".
    Normalize dates to decade before checking.
  - Abbreviations: transcript "Bletchley Park"; summary "BP". No match -> false positive.

Implementation sketch (add to run_eval.py when recorder produces JSON summaries):

  import re
  def check_hallucinations(transcript: str, summary: str) -> list[str]:
      proper_nouns = re.findall(r'(?<=[.!?] )([A-Z][a-z]+(?:\\s+[A-Z][a-z]+)*)', summary)
      years = re.findall(r'\\b(19|20)\\d{2}\\b', summary)
      flagged = []
      for entity in set(proper_nouns + years):
          if entity.lower() not in transcript.lower():
              flagged.append(entity)
      return sorted(set(flagged))
"""

# ---------------------------------------------------------------------------
# Hallucination check: real implementation
# ---------------------------------------------------------------------------

# Anchored entities: capitalized multi-word names, years, numbers, dates.
# Excludes sentence-leading capitalized words and pronouns.
_PROPER_NOUN_RE = re.compile(
    r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b"
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_DATE_RE = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?(?:%|k|m|bn)?\b")
_PRONOUN_BLACKLIST = {
    "I", "We", "You", "They", "He", "She", "It", "Yes", "No", "Okay",
    "Speaker", "Action", "Decisions", "Summary", "Open", "Questions",
    "None", "Recorded", "Transcript",
    # Common sentence-leading verbs/wh-words that get capitalized after
    # bullet/colon boundaries in summaries (e.g. `**Sean**: Determine if...`).
    # Without these, every action item triggers a false hallucination flag.
    "Add", "Determine", "Create", "Handle", "Update", "Confirm", "Check",
    "Review", "Schedule", "Send", "Prepare", "Identify", "Implement",
    "Ensure", "Provide", "Set", "Ask", "Continue", "Follow", "Reach",
    "Coordinate", "Investigate", "Discuss", "Decide", "Build", "Test",
    "Finalize", "Document", "Track", "Verify", "When", "Where", "What",
    "Why", "How", "Who", "Will", "Should", "Can", "Need", "Make",
    "Unassigned",
}


def _extract_anchored_entities(text: str) -> set[str]:
    """Return the set of anchored entities in `text` worth checking against
    the source transcript: proper nouns, years, dates, numbers."""
    entities: set[str] = set()
    for m in _PROPER_NOUN_RE.findall(text):
        if m.split()[0] not in _PRONOUN_BLACKLIST and len(m) > 1:
            entities.add(m.strip())
    for m in _YEAR_RE.findall(text):
        # findall returns the group prefix; reconstruct by re-matching
        pass
    # Simpler: re-scan for full year matches
    for m in re.finditer(r"\b(?:19|20)\d{2}\b", text):
        entities.add(m.group(0))
    for m in _DATE_RE.findall(text):
        entities.add(m if isinstance(m, str) else " ".join(m))
    for m in _NUMBER_RE.findall(text):
        if len(m) >= 2:  # skip single digits (too noisy)
            entities.add(m)
    return entities


def cmd_hallucination(source_path: Path, summary_path: Path) -> int:
    """Flag entities in summary that don't appear in source transcript."""
    if not source_path.exists():
        log.error("source not found: %s", source_path)
        return 1
    if not summary_path.exists():
        log.error("summary not found: %s", summary_path)
        return 1
    source = source_path.read_text(encoding="utf-8").lower()
    summary_full = summary_path.read_text(encoding="utf-8")
    # Strip frontmatter + meta-italics from summary so we don't flag e.g.
    # the model-name line as a hallucination.
    summary_body = []
    in_fm = False
    for ln in summary_full.splitlines():
        s = ln.strip()
        if s == "---":
            in_fm = not in_fm
            continue
        if in_fm:
            continue
        if s.startswith("_") and s.endswith("_") and len(s) > 2:
            continue
        if s.startswith("# ") or s.startswith("## "):
            continue
        summary_body.append(ln)
    summary = "\n".join(summary_body)

    entities = _extract_anchored_entities(summary)
    flagged: list[tuple[str, str]] = []
    confirmed: list[str] = []
    # Word-boundary check (Flaw D from /flaws audit): naive substring `in`
    # gives false-negatives like "May" matching "maybe" or "monday" in
    # "moonday". Use \b on both sides AND require the multi-word entity to
    # appear as a contiguous run of word-boundary-bounded tokens.
    source_lower = source.lower()
    for e in sorted(entities):
        e_lower = e.lower()
        # Build a regex that matches the entity as whole words; allow
        # arbitrary whitespace between sub-tokens (the source may have
        # different punctuation/line breaks).
        parts = [re.escape(p) for p in e_lower.split()]
        pattern = r"\b" + r"\W+".join(parts) + r"\b"
        if re.search(pattern, source_lower):
            confirmed.append(e)
        else:
            # Find the sentence in the summary containing this entity
            ctx = ""
            for sentence in re.split(r"(?<=[.!?])\s+", summary):
                if e in sentence:
                    ctx = sentence.strip()
                    break
            flagged.append((e, ctx))

    print(f"\nHallucination check: {summary_path.name}")
    print(f"Source: {source_path.name}")
    print(f"  entities checked:  {len(entities)}")
    print(f"  confirmed in src:  {len(confirmed)}")
    print(f"  not in src (FLAG): {len(flagged)}")
    if flagged:
        print("\nFlagged entities:")
        for e, ctx in flagged:
            print(f"  • {e!r}")
            if ctx:
                print(f"      in: {ctx[:100]}")
    return 0 if not flagged else 2


# ---------------------------------------------------------------------------
# Search recall: real implementation
# ---------------------------------------------------------------------------

def cmd_search_recall() -> int:
    """Inject N known queries into the FTS5 index, run them, measure hit rate.

    Method:
      1. Pull a sample of distinctive 3-5-word phrases from each transcript
         in ~/recordings (excluding meta-banner lines)
      2. Run `recorder search <phrase>` for each
      3. Hit if the result includes that recording's name
      4. Recall = hits / queries

    A phrase is "distinctive" if it appears in only one recording.
    """
    out_dir = Path(os.environ.get(
        "MEETING_DIR", str(Path.home() / "recordings")))
    md_files = sorted(p for p in out_dir.glob("*.offline.md")
                      if not p.name.endswith(".summary.md"))
    if len(md_files) < 1:
        log.error("no .offline.md files in %s; run a meeting first", out_dir)
        return 1

    # Build inverse-index of phrases to recording names.
    phrase_owners: dict[str, set[str]] = {}
    name_phrases: dict[str, list[str]] = {}
    for md in md_files:
        name = md.stem.replace(".offline", "")
        text = md.read_text(encoding="utf-8")
        # Strip header
        body = "\n".join(
            ln for ln in text.splitlines()
            if not ln.strip().startswith("#")
            and not (ln.strip().startswith("---") or ln.strip().startswith("_"))
        )
        words = re.findall(r"[A-Za-z][A-Za-z']*", body)
        # 4-word distinctive phrases (long enough to be unique, short enough to grep)
        phrases = []
        for i in range(0, len(words) - 4):
            phrase = " ".join(words[i:i + 4])
            phrases.append(phrase)
            phrase_owners.setdefault(phrase.lower(), set()).add(name)
        name_phrases[name] = phrases

    # Filter to phrases that occur in exactly one recording
    distinctive = {
        p: list(owners)[0]
        for p, owners in phrase_owners.items()
        if len(owners) == 1
    }
    if not distinctive:
        log.error("no distinctive phrases found across %d recordings", len(md_files))
        return 1
    log.info("found %d distinctive phrases across %d recordings",
             len(distinctive), len(md_files))

    # Sample 5 phrases per recording (or fewer)
    import random
    rng = random.Random(42)
    sampled: list[tuple[str, str]] = []
    by_owner: dict[str, list[str]] = {}
    for phrase, owner in distinctive.items():
        by_owner.setdefault(owner, []).append(phrase)
    for owner, phrases in by_owner.items():
        for p in rng.sample(phrases, min(5, len(phrases))):
            sampled.append((p, owner))

    log.info("running %d search queries ...", len(sampled))

    # Reindex first
    subprocess.run(
        ["recorder", "search", "--reindex"],
        capture_output=True, timeout=60,
        env={**os.environ, "MEETING_DIR": str(out_dir)},
    )

    hits = 0
    for phrase, expected_owner in sampled:
        r = subprocess.run(
            ["recorder", "search", phrase, "--limit", "5"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "MEETING_DIR": str(out_dir)},
        )
        # `recorder search` prints recording names; check expected_owner is in output
        if expected_owner in r.stdout:
            hits += 1
        else:
            log.debug("MISS: query=%r expected=%s output=%r",
                      phrase, expected_owner, r.stdout[:200])

    recall = hits / len(sampled) if sampled else 0
    print(f"\nSearch recall eval:")
    print(f"  recordings:   {len(md_files)}")
    print(f"  queries:      {len(sampled)}")
    print(f"  hits:         {hits}")
    print(f"  recall:       {recall * 100:.1f}%")
    return 0 if recall > 0.8 else 2


# ---------------------------------------------------------------------------
# Polish A/B: real implementation
# ---------------------------------------------------------------------------

def cmd_diarize_stability(flac_path: Path, runs: int = 2,
                          threshold: Optional[float] = None) -> int:
    """Run sherpa-onnx diarization N times on the same FLAC, measure
    consistency. A diarizer that's sensitive to threshold or initialization
    will fluctuate; a stable one will produce the same speaker_count and
    similar segment boundaries. We don't have RTTM ground truth for our
    real meetings, but self-consistency is a useful health signal.

    Reports per run: detected speakers, segment count, total speech time.
    Then: variance across runs, plus a turn-boundary IoU (intersection-over-
    union of segment boundaries) if runs >= 2.
    """
    if not flac_path.exists():
        log.error("flac not found: %s", flac_path)
        return 1

    out_dir = flac_path.parent
    name = flac_path.stem
    json_path = out_dir / f"{name}.diarized.json"
    md_path = out_dir / f"{name}.diarized.md"

    results: list[dict] = []
    for i in range(runs):
        log.info("diarize run %d/%d ...", i + 1, runs)
        # Force overwrite each run; sherpa is deterministic but we want to
        # measure cross-run variance under different process-startup conditions.
        cmd = ["recorder", "diarize", str(flac_path), "--force"]
        if threshold is not None:
            cmd += ["--threshold", str(threshold)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            log.error("diarize run %d failed: rc=%d stderr=%s",
                      i + 1, r.returncode, r.stderr[-200:])
            return 1
        if not json_path.exists():
            log.error("diarized.json missing after run %d", i + 1)
            return 1
        d = json.loads(json_path.read_text(encoding="utf-8"))
        spans = d.get("speaker_spans", [])
        speakers = d.get("speakers_detected", 0)
        total_speech = sum(s["end"] - s["start"] for s in spans)
        results.append({
            "run": i + 1,
            "speakers": speakers,
            "segments": len(spans),
            "speech_s": total_speech,
            "spans": spans,
        })

    print(f"\nDiarization stability: {flac_path.name}")
    print(f"  threshold:  {threshold if threshold is not None else 'default'}")
    print(f"  runs:       {runs}")
    for r in results:
        print(f"  run {r['run']}: {r['speakers']:3} speakers, "
              f"{r['segments']:4} segs, {r['speech_s']:.1f}s speech")

    if runs >= 2:
        # Cross-run variance on counts
        spk_counts = [r["speakers"] for r in results]
        seg_counts = [r["segments"] for r in results]
        speech_secs = [r["speech_s"] for r in results]
        spk_var = max(spk_counts) - min(spk_counts)
        seg_var = max(seg_counts) - min(seg_counts)
        speech_var = max(speech_secs) - min(speech_secs)
        print(f"\n  speakers Δ: {spk_var}")
        print(f"  segments Δ: {seg_var}")
        print(f"  speech Δ:   {speech_var:.2f}s")

        # Boundary IoU: union/intersection of all 1-second buckets per run
        def buckets(spans):
            s = set()
            for span in spans:
                start = int(span["start"])
                end = int(span["end"]) + 1
                for t in range(start, end):
                    s.add(t)
            return s
        a = buckets(results[0]["spans"])
        b = buckets(results[-1]["spans"])
        iou = len(a & b) / len(a | b) if (a | b) else 1.0
        print(f"  boundary IoU (run1 vs run{runs}): {iou * 100:.1f}%")
    return 0


def cmd_polish_ab(source_path: Path, ref_path: Optional[Path] = None) -> int:
    """Run gemma4 polish on `source_path` and compare WER vs the reference
    (the source itself if no ref). Reports:
      - raw vs polished word count
      - polished WER vs ref (lower = polish converged toward ref)
      - entity preservation rate (proper nouns in raw vs polished)
    """
    if not source_path.exists():
        log.error("source not found: %s", source_path)
        return 1
    raw = source_path.read_text(encoding="utf-8")
    raw_body = "\n".join(
        ln for ln in raw.splitlines()
        if not ln.strip().startswith("#") and not ln.strip().startswith("---")
        and not (ln.strip().startswith("_") and ln.strip().endswith("_"))
    ).strip()

    log.info("running `recorder polish %s` ...", source_path.name)
    out_path = source_path.with_suffix(".polish-ab.md")
    r = subprocess.run(
        ["recorder", "polish", str(source_path), "-o", str(out_path)],
        capture_output=True, text=True, timeout=600,
    )
    if r.returncode != 0 or not out_path.exists():
        log.error("polish failed rc=%d stderr=%s", r.returncode, r.stderr[-200:])
        return 1
    polished_body = out_path.read_text(encoding="utf-8")
    # Strip the polish header comment
    polished_body = re.sub(r"^<!--.*?-->\n+", "", polished_body, flags=re.DOTALL)

    print(f"\nPolish A/B: {source_path.name}")
    print(f"  raw words:      {len(raw_body.split())}")
    print(f"  polished words: {len(polished_body.split())}")

    if ref_path and ref_path.exists():
        ref_text = ref_path.read_text(encoding="utf-8")
        wer_raw = compute_wer(raw_body, ref_text)
        wer_pol = compute_wer(polished_body, ref_text)
        if wer_raw is not None and wer_pol is not None:
            delta = (wer_raw - wer_pol) * 100
            sign = "+" if delta >= 0 else ""
            print(f"  WER raw:        {wer_raw * 100:.1f}%")
            print(f"  WER polished:   {wer_pol * 100:.1f}%")
            print(f"  delta:          {sign}{delta:.1f}pp "
                  f"(positive = polish helped)")
        else:
            print("  WER: could not compute")

    # Entity preservation: how many proper nouns in raw survived to polished?
    raw_entities = _extract_anchored_entities(raw_body)
    pol_entities = _extract_anchored_entities(polished_body)
    preserved = raw_entities & pol_entities
    dropped = raw_entities - pol_entities
    added = pol_entities - raw_entities
    if raw_entities:
        rate = len(preserved) / len(raw_entities)
        print(f"  entity preservation: {rate * 100:.1f}% "
              f"({len(preserved)}/{len(raw_entities)})")
        if dropped:
            print(f"  dropped: {sorted(dropped)[:8]}")
        if added:
            print(f"  added (CAUTION — may be hallucinations): {sorted(added)[:8]}")
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="recorder eval harness")
    parser.add_argument("--corpus", default=None, help="corpus directory (default: ~/recordings/test-corpus)")
    parser.add_argument("--clip", default=None, help="run only this clip ID (e.g. L1)")
    parser.add_argument("--skip-live", action="store_true", help="skip streaming mode (faster)")
    parser.add_argument("--design-only", action="store_true",
                        help="print A/B polish and hallucination check designs, then exit")
    parser.add_argument("--output", default=None,
                        help="output .md path (default: evals/results-YYYY-MM-DD.md)")
    parser.add_argument("--label", default=None,
                        help="row label for sweep mode; appends a row to "
                             "evals/sweep-YYYY-MM-DD.md instead of writing a "
                             "fresh report. Use this to compare multiple configs.")
    parser.add_argument("--sweep-file", default=None,
                        help="explicit path for --label append (default: "
                             "evals/sweep-YYYY-MM-DD.md)")
    parser.add_argument(
        "--mode", default="wer",
        choices=["wer", "hallucination", "search-recall", "polish-ab",
                 "diarize-stability"],
        help="eval mode: wer (default, live vs offline WER), "
             "hallucination (proper-nouns/dates in summary not in source), "
             "search-recall (inject phrases, query, measure hit-rate), "
             "polish-ab (run recorder polish on a transcript, compare WER), "
             "diarize-stability (run diarize N times on a FLAC, measure variance)",
    )
    parser.add_argument(
        "--source", default=None,
        help="for hallucination/polish-ab: path to source transcript .md/.txt",
    )
    parser.add_argument(
        "--summary", default=None,
        help="for hallucination: path to .summary.md to check",
    )
    parser.add_argument(
        "--flac", default=None,
        help="for diarize-stability: path to FLAC",
    )
    parser.add_argument(
        "--runs", type=int, default=2,
        help="for diarize-stability: number of runs (default 2)",
    )
    parser.add_argument(
        "--threshold", type=float, default=None,
        help="for diarize-stability: clustering threshold (default: recorder's default)",
    )
    args = parser.parse_args()

    if args.design_only:
        print(POLISH_AB_DESIGN)
        print(HALLUCINATION_DESIGN)
        return

    # Dispatch alternate eval modes (no corpus traversal needed).
    if args.mode == "hallucination":
        # Per-pair: --source X --summary Y
        # Or corpus: --corpus <toml> sweeps clips that have BOTH a frozen
        # ref_transcript AND a sibling .summary.md (auto-derived).
        pairs: list[tuple[Path, Path]] = []
        if args.source and args.summary:
            pairs = [(Path(args.source).expanduser(),
                      Path(args.summary).expanduser())]
        elif args.corpus:
            corpus_path = Path(args.corpus).expanduser()
            corpus_dir = corpus_path.parent if corpus_path.is_file() else corpus_path
            corpus_toml = corpus_path if corpus_path.is_file() else corpus_path / "corpus.toml"
            for clip in load_corpus(corpus_toml=corpus_toml, corpus_dir=corpus_dir):
                if not (clip.ref_transcript and clip.ref_transcript.exists()):
                    continue
                # Convention: <stem>.summary.md sibling
                stem = clip.ref_transcript.stem.replace(".offline-frozen", "")
                summary = clip.ref_transcript.parent / f"{stem}.summary.md"
                if summary.exists():
                    pairs.append((clip.ref_transcript, summary))
        if not pairs:
            log.error("--mode hallucination requires --source + --summary OR "
                      "--corpus with sibling .summary.md per clip")
            sys.exit(2)
        rc = 0
        flagged_total = 0
        for src, summ in pairs:
            print(f"\n--- {summ.name} ---")
            r = cmd_hallucination(src, summ)
            if r == 2:
                flagged_total += 1
            elif r != 0:
                rc = r
        if flagged_total:
            print(f"\n{flagged_total} of {len(pairs)} summaries had flagged entities")
        sys.exit(rc)
    if args.mode == "search-recall":
        sys.exit(cmd_search_recall())
    if args.mode == "polish-ab":
        # Per-source mode: --source <one transcript>
        # OR corpus mode: --corpus <toml> sweeps all clips' frozen refs
        sources: list[Path] = []
        if args.source:
            sources = [Path(args.source).expanduser()]
        elif args.corpus:
            # Use each clip's ref_transcript as the input to polish-ab
            corpus_path = Path(args.corpus).expanduser()
            corpus_dir = corpus_path.parent if corpus_path.is_file() else corpus_path
            corpus_toml = corpus_path if corpus_path.is_file() else corpus_path / "corpus.toml"
            for clip in load_corpus(corpus_toml=corpus_toml, corpus_dir=corpus_dir):
                if clip.ref_transcript and clip.ref_transcript.exists():
                    sources.append(clip.ref_transcript)
        if not sources:
            log.error("--mode polish-ab requires --source <transcript> or "
                      "--corpus <toml> with ref_transcript per clip")
            sys.exit(2)
        rc = 0
        for s in sources:
            print(f"\n--- {s.name} ---")
            r = cmd_polish_ab(s, ref_path=s)
            if r != 0:
                rc = r
        sys.exit(rc)
    if args.mode == "diarize-stability":
        if not args.flac:
            log.error("--mode diarize-stability requires --flac <path>")
            sys.exit(2)
        sys.exit(cmd_diarize_stability(
            Path(args.flac).expanduser(),
            runs=args.runs, threshold=args.threshold,
        ))

    # --corpus may be a .toml file or a directory containing corpus.toml.
    corpus_toml: Optional[Path] = None
    corpus_dir = CORPUS_DIR
    if args.corpus:
        p = Path(args.corpus).expanduser()
        if p.is_file():
            corpus_toml = p
            corpus_dir = p.parent
        elif p.is_dir():
            corpus_dir = p
            if (p / "corpus.toml").exists():
                corpus_toml = p / "corpus.toml"
        else:
            log.error("--corpus path not found: %s", p)
            sys.exit(1)

    clips = load_corpus(clip_filter=args.clip,
                        corpus_toml=corpus_toml, corpus_dir=corpus_dir)
    if not clips:
        print(f"No clips found in {corpus_dir}. Run setup.sh first.", file=sys.stderr)
        sys.exit(1)

    # Filter to clips whose audio file exists; warn about missing ones
    runnable = []
    for clip in clips:
        # Resolve relative paths against corpus_dir
        if not clip.path.is_absolute():
            clip.path = corpus_dir / clip.path
        if clip.ref_transcript and not clip.ref_transcript.is_absolute():
            clip.ref_transcript = corpus_dir / clip.ref_transcript
        if clip.ref_rttm and not clip.ref_rttm.is_absolute():
            clip.ref_rttm = corpus_dir / clip.ref_rttm
        if clip.path.exists():
            runnable.append(clip)
        else:
            print(f"  SKIP {clip.id}: audio not found at {clip.path}", file=sys.stderr)

    if not runnable:
        print("No audio files found. Run setup.sh and complete manual downloads.", file=sys.stderr)
        sys.exit(1)

    print(f"Running eval on {len(runnable)} clip(s) ...")
    results = []
    for clip in runnable:
        print(f"[{clip.id}] {clip.notes}")
        result = eval_clip(clip, skip_live=args.skip_live)
        results.append(result)

    # Console summary. live_vs_offline is the most-honest column:
    # both transcripts come from THIS run, so the comparison is internally
    # consistent regardless of whether the frozen reference has drifted.
    print("")
    print(f"{'Clip':<14} {'Dur':>6} {'Live WER':>9} {'Off WER':>9} "
          f"{'Live-vs-Off':>11} {'DER':>7}")
    print("-" * 64)
    for r in results:
        dur = f"{r.duration_s:.0f}s" if r.duration_s else "   -"
        print(
            f"{r.clip_id:<14} {dur:>6} "
            f"{format_pct(r.live_wer):>9} "
            f"{format_pct(r.offline_wer):>9} "
            f"{format_pct(r.live_vs_offline_wer):>11} "
            f"{format_pct(r.der):>7}"
        )
        for err in r.errors:
            print(f"         ! {err}")

    # Aggregate stats across clips (only meaningful with >=2 clips).
    runnable_results = [r for r in results
                        if r.live_wer is not None or r.offline_wer is not None]
    if len(runnable_results) >= 2:
        def _avg(vals):
            xs = [v for v in vals if v is not None]
            return sum(xs) / len(xs) if xs else None

        def _dur_weighted_avg(getter):
            num, den = 0.0, 0.0
            for r in runnable_results:
                v = getter(r)
                if v is None or r.duration_s is None:
                    continue
                num += v * r.duration_s
                den += r.duration_s
            return num / den if den else None

        live_avg = _avg(r.live_wer for r in runnable_results)
        off_avg = _avg(r.offline_wer for r in runnable_results)
        lvo_avg = _avg(r.live_vs_offline_wer for r in runnable_results)
        live_dur = _dur_weighted_avg(lambda r: r.live_wer)
        off_dur = _dur_weighted_avg(lambda r: r.offline_wer)
        lvo_dur = _dur_weighted_avg(lambda r: r.live_vs_offline_wer)
        print("-" * 64)
        print(
            f"{'avg':<14} {'':>6} "
            f"{format_pct(live_avg):>9} "
            f"{format_pct(off_avg):>9} "
            f"{format_pct(lvo_avg):>11} {'':>7}"
        )
        if any(x is not None for x in (live_dur, off_dur, lvo_dur)):
            print(
                f"{'avg (sec-wt)':<14} {'':>6} "
                f"{format_pct(live_dur):>9} "
                f"{format_pct(off_dur):>9} "
                f"{format_pct(lvo_dur):>11} {'':>7}"
            )

    # Write report
    today = datetime.date.today().isoformat()
    if args.label:
        # Sweep mode: append a single row per (label, clip) pair so a shell
        # loop can produce a comparison table without each invocation
        # clobbering the previous one.
        sweep_path = (
            Path(args.sweep_file) if args.sweep_file
            else EVALS_DIR / f"sweep-{today}.md"
        )
        new_file = not sweep_path.exists()
        with sweep_path.open("a", encoding="utf-8") as f:
            if new_file:
                f.write(f"# recorder sweep -- {today}\n\n")
                f.write("| label | clip | dur | live WER | off WER | gain | DER |\n")
                f.write("|---|---|---|---|---|---|---|\n")
            for r in results:
                dur = f"{r.duration_s:.0f}s" if r.duration_s else "—"
                f.write(
                    f"| `{args.label}` | {r.clip_id} | {dur} "
                    f"| {format_pct(r.live_wer).strip()} "
                    f"| {format_pct(r.offline_wer).strip()} "
                    f"| {format_pct(r.offline_gain).strip()} "
                    f"| {format_pct(r.der).strip()} |\n"
                )
        log.info("appended %d row(s) to %s", len(results), sweep_path)
    else:
        output_path = Path(args.output) if args.output else (EVALS_DIR / f"results-{today}.md")
        write_report(results, output_path)


if __name__ == "__main__":
    main()
