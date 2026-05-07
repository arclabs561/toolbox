# recorder evals

## Overview

Eval harness for the `recorder` transcription tool (parakeet-mlx ASR +
sherpa-onnx diarization + gemma4 polish/summary). Measures word error rate,
diarization error rate, and streaming-vs-offline gap on a 10-clip corpus.
Does not run automatically in CI; run manually before shipping ASR model or
diarization threshold changes.

## Quick start

```bash
# 1. fetch corpus (automated clips only; see setup.sh for manual steps)
bash ~/recordings/test-corpus/setup.sh

# 2. run eval (skip live mode for a faster first pass)
uv run evals/run_eval.py --skip-live

# 3. run both modes (takes ~20 min for full corpus)
uv run evals/run_eval.py

# 4. run a single clip
uv run evals/run_eval.py --clip L1

# 5. print A/B polish and hallucination check designs
uv run evals/run_eval.py --design-only
```

Output is written to `evals/results-YYYY-MM-DD.md`.

## Dependencies

PEP 723 inline metadata is at the top of `run_eval.py`. `uv run` resolves them
automatically. Direct install:

```bash
pip install jiwer "pyannote.metrics>=3.2"
```

`recorder` must be on PATH and accept:
- `recorder --from-file <path> --json` (streaming mode)
- `recorder redo <path> --json` (offline full-attention mode)

Both must write JSON to stdout with a `"transcript"` key. If your CLI writes
differently, edit `run_recorder_live` and `run_recorder_offline` in `run_eval.py`.

## What it measures

| Axis | Metric | Ground truth needed |
|------|--------|-------------------|
| 1. Streaming ASR quality | WER vs reference transcript | Yes (clips L1, L2, S1, S2) |
| 2. Offline ASR quality | WER vs reference transcript | Yes |
| 3. Streaming vs offline gap | WER(live) - WER(offline) | Yes |
| 4. Speaker diarization | DER (pyannote.metrics, collar=0.25s) | RTTM (clips A1, A2, V1, V2) |
| 5. Pause markers | Not computed; inspect transcript JSON manually | No |
| 6. Polish edit impact | A/B design only; see --design-only output | Yes |
| 7. Summary hallucination | Hallucination check design; see --design-only | No |
| 8. Search recall | Not in this harness; test via recorder search CLI | No |
| 9. Dictation accuracy | Use clips L1, L2 with push-to-talk flag if supported | Yes |

## WER alignment pitfalls

WER is computed by `jiwer` with lowercase + punctuation strip normalization. This is
standard but has documented failure modes:

- **Contractions**: "it's" vs "its" are different words after normalization. Expect
  ~0.5-1 WER point inflation on conversational clips.
- **Number surface forms**: "1913" vs "nineteen thirteen" inflates WER by 2 word
  positions (deletion + insertion). LibriSpeech refs spell out numbers; parakeet
  may output digits.
- **Filler words**: LibriSpeech refs omit "um"/"uh"; if parakeet transcribes them,
  WER rises without the output being "wrong" in conversational use.
- **Capitalization in entity correction**: jiwer strips case, so CAP edits from
  polish are invisible to WER. A case-sensitive WER variant would surface them.

WER on LibriSpeech dev-clean is a clean-speech ceiling. Expect:
- Parakeet-mlx streaming mode: ~4-8% WER on dev-clean (local-attention constraint)
- Parakeet-mlx offline mode: ~2-4% WER on dev-clean (full-attention)
- Gap of 2-5% WER is expected; the "Cross Camp"/"Chris Kemp" class is low-frequency
  but high-impact -- WER understates it since it's one word substitution in a long clip.

## DER interpretation

DER is computed using pyannote.metrics with collar=0.25s (NIST standard for
meeting corpora). A DER of 0.20 (20%) is a reasonable baseline for
sherpa-onnx pyannote on AMI headset audio.

DER components (shown if you set `detailed=True` in compute_der):
- Missed speech (reference segment not covered)
- False alarm (hypothesis segment with no reference match)
- Speaker confusion (correct segment, wrong speaker label)

Threshold tuning goal: minimize confusion without increasing missed speech.
Run at 3+ threshold values (e.g. 0.3, 0.5, 0.7) and plot the DER curve.

**Overlap handling**: the current harness does not use `skip_overlap=True`.
VoxConverse clips have heavy overlap; DER on those clips will be higher and
should be interpreted as "overlap-inclusive DER", not a fair comparison to
AMI single-headset clips.

## Pause markers

`recorder` inserts `[pause 2.3s]` style markers based on segment timestamps.
These are not evaluated here; inspect the transcript JSON manually for
`"type": "pause"` entries and verify they align with audible gaps in the audio.
Threshold is tunable; suggested test: clip with a long natural silence (>3s) vs
one with dense speech.

## Polish A/B eval (design only)

Run `uv run evals/run_eval.py --design-only` for the full design. Short version:
compare WER(raw parakeet) vs WER(polished) using `recorder redo --no-polish` flag.
The adversarial case is a SUB edit that replaces a correctly-transcribed proper noun
with a plausible but wrong one. Entity preservation rate (proper nouns in reference
that survive into hypothesis) is a better metric than WER alone for this class.

## Summary hallucination check (design only)

See `--design-only` output. The check greps for capitalized tokens and year-format
dates in the summary that have no match (case-insensitive substring) in the source
transcript. False positives are expected from anaphora and paraphrases; treat output
as a review list, not a pass/fail gate.

## Adding clips

Add an entry to `corpus.toml` (create it if absent, mirroring the Python dict shape
in `run_eval.py`). Fields: `id`, `path` (relative to corpus dir), `duration_s`,
`speakers`, `ref_transcript` (optional), `ref_rttm` (optional), `notes`.

## Known limits

- No silence/noise-robustness test (no clip with background noise or music)
- No non-English test (parakeet is EN-only; not tested)
- No domain-specific vocabulary test beyond Spoken Wikipedia and Sherlock Holmes
- DER does not separate confusion from missed speech in the table; use pyannote
  metrics `detailed` mode for per-component breakdown
- `run_recorder_live` has a 600s timeout; long clips (AMI ~30 min) need `--skip-live`
  or a higher timeout
