# recorder eval design

## Overview

Four unmeasured axes require explicit measurement protocols before the eval
harness in `run_eval.py` can be considered complete. This doc describes the
methodology for each. Implementation goes in `run_eval.py`; this doc is the
pre-implementation contract.

---

## 1. Polish A/B fidelity

**What we want to know**: does gemma4 polish improve WER and entity accuracy, or
introduce regressions (hallucinated name substitutions)?

### Method

1. For each clip with a reference transcript, run recorder twice:
   - `recorder redo <clip> --no-polish --json` -> `raw_transcript`
   - `recorder redo <clip> --json` -> `polished_transcript`
2. Compute WER(raw) and WER(polished) against the reference using jiwer with
   standard normalization (lowercase, strip punctuation).
3. Compute entity preservation rate (EPR): extract proper-noun tokens from the
   reference using a simple heuristic (capitalized tokens, 2+ chars, not
   sentence-initial), then check fraction that appear in hypothesis (case-insensitive
   substring match).

### Metrics

| Metric | Formula | Pass threshold |
|--------|---------|---------------|
| WER delta | WER(polished) - WER(raw) | < +0.5pp (polish should not hurt) |
| EPR delta | EPR(polished) - EPR(raw) | > 0 (polish should preserve or improve) |
| Substitution rate | SUB edits / reference words | Track; no hard threshold |

### Adversarial case

The "Cross Camp / Chris Kemp" class is a polish substitution: a correctly-transcribed
rare name replaced by a plausible common name. WER captures this as one SUB event
(1/N WER contribution) even though it is a semantic error. The EPR metric surfaces
it directly: the reference name is no longer in the hypothesis.

Target clips: S1 (Niels Bohr), S2 (Alan Turing), P1 (Ada Lovelace), any real-meeting
clip where a rare proper noun is known from context.

### CLI flag assumption

Assumes `recorder redo --no-polish` exists. If not, add it before wiring this eval.
Alternative: pipe raw parakeet output through the eval without the polish step.

---

## 2. Summary hallucination check

**What we want to know**: does gemma4 summary invent dates, numbers, names, or
agenda items not present in the source transcript?

### Method

1. Run `recorder redo <clip> --json` to get `transcript` and `summary` fields.
2. Extract "checkable tokens" from the summary:
   - Year-format dates: `\b(19|20)\d{2}\b`
   - Named entities: capitalized tokens 3+ chars, not sentence-initial (heuristic)
   - Cardinal numbers: `\b\d{2,}\b` (skip single digits)
3. For each checkable token, test membership in the source transcript via
   case-insensitive substring match.
4. Report hallucination rate = tokens NOT found in transcript / total checkable tokens.

### Caveats

- False positives: anaphora ("the committee" summarized as "the Finance Committee"),
  paraphrase, and common proper nouns (city names) that appear in training data but
  not the clip. Treat output as a review list, not a pass/fail binary.
- The check requires a reasonably long transcript (>200 words). Short clips produce
  noise due to sparse reference.

### Target clips

Q1 (Hansard) and R1 (earnings call) are the highest-signal sources because their
ground truth contains machine-verifiable tokens (bill IDs, revenue figures, vote counts).
Real-meeting clip P2 from the base corpus (the "Chris Kemp" meeting) can also be used
with manual reference review.

---

## 3. Diarization DER computation

**Already partially implemented in run_eval.py. This section documents the intended
full protocol including the extended-v2 sources.**

### Method

Use `pyannote.metrics.diarization.DiarizationErrorRate` with:
- `collar = 0.25` (NIST standard for meeting corpora)
- `skip_overlap = False` (report overlap-inclusive DER; note this in results)

### Threshold sweep

Run at three clustering thresholds (e.g. 0.3, 0.5, 0.7) and report DER at each.
The goal is to find the threshold that minimizes confusion without inflating
missed speech or false alarm. Plot DER curve per clip family:
- AMI headset (close-talk, low noise): expect DER 10-20%
- VoxConverse (in-the-wild): expect DER 20-35% (heavy overlap)
- DIHARD-III (mixed domain): expect DER 25-40%

### Per-component reporting

Always report the three DER components separately:
1. Missed speech (reference not covered)
2. False alarm (hypothesis with no reference)
3. Speaker confusion (correct segment, wrong label)

Confusion is the target for threshold tuning. Missed speech and false alarm
are affected by VAD, not clustering threshold.

### New sources (extended-v2)

| Clip ID | Source | RTTM | Expected DER range | Notes |
|---------|--------|------|--------------------|-------|
| V1 | VoxConverse aepyx | joonson/voxconverse or Zenodo 3740391 | 25-35% | Overlap-heavy |
| V2 | VoxConverse bfkdi | Same | 20-30% | Fewer speakers |
| DH1 | DIHARD-III dev clip (2-3 selected) | Zenodo 4725974 | 25-40% | Mixed domain |
| A1/A2 | AMI ES2002a / IS1009b | BUTspeechFIT GitHub | 10-20% | Close-talk ceiling |

---

## 4. Dictation latency (push-to-talk)

**What we want to know**: cold-start vs warm latency for push-to-talk mode; how
does clip duration affect first-word latency?

### Method

1. Cold start: restart the recorder process (or clear any model cache) between runs.
2. Warm start: second run of the same clip with process still resident.
3. Measure:
   - `t_first_word`: wall time from audio-capture-start to first word emitted to stdout
   - `t_full`: wall time from audio-capture-start to final transcript token
4. Compute real-time factor (RTF) = t_full / clip_duration. RTF < 1.0 means faster than real-time.

### CLI assumption

Requires a `--time-mode` flag or wrapper that inserts timing markers into JSON output.
Alternative: wrap the CLI invocation in Python `time.perf_counter()` and parse the
first token timestamp from the JSON stream.

### Target clips

Short clips (L1 14s, L2 9s, short-dictation 5-30s) for latency sensitivity.
Long clips (A1 30min) for RTF at scale. Report both.

---

## 5. Search recall (reference design only)

Not implemented in the harness. Protocol for future `run_eval.py` addition:

1. Construct 5-10 synthetic queries from known meeting content
   (e.g. "when did Alice mention the budget?" for a clip where Alice says "budget" at T=4:23).
2. Run `recorder search <query> --json` against an indexed recording.
3. Score: did the top-1 result land within 30s of the reference timestamp?

Requires the search index to be pre-built from the eval clips. Defer until the
search CLI is stable.

---

## Execution order for run_eval.py integration

1. DER computation (already partial; add DIHARD clips and threshold sweep)
2. Polish A/B (add `--no-polish` flag and EPR metric)
3. Summary hallucination (add token-extraction + membership check)
4. Dictation latency (add timing wrapper)
5. Search recall (defer)
