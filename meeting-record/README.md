# meeting-record

A personal local Whisper-class stack for Apple Silicon. Two workflows:

1. **Dictate** — push-to-talk → transcript on your clipboard. SuperWhisper-style, but local, free, and yours.
2. **Record** — full meeting capture with live web UI, speaker diarization, summary, search across past meetings.

All local. No cloud. No data leaves your machine.

Stack: [parakeet-mlx](https://github.com/senstella/parakeet-mlx) for ASR, [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) for diarization, [Ollama](https://ollama.com) for summary + cleanup.

The binary is named `meeting-record` for historical reasons; `dictate` is a first-class subcommand.

## Setup

```sh
brew install ffmpeg
# optional, for system-audio capture (Zoom/Meet remote-participant audio):
brew install --cask blackhole-2ch
# optional, for --summary:
ollama pull gemma4:e2b   # or gemma4:latest if you have headroom
```

First run downloads the parakeet model (~600MB) into `~/.cache/huggingface/`. First `--diarize` run downloads ~35MB of sherpa-onnx models into `~/.cache/meeting-record/`. The terminal app needs Microphone permission (System Settings > Privacy & Security > Microphone) — the watchdog warns within 5 seconds if access was denied.

## Usage

### Dictation (push-to-talk)

```sh
meeting-record dictate            # Enter to start, Enter again to stop
meeting-record dictate --polish   # gemma4 cleanup before clipboard
meeting-record dictate --save     # also keep .flac + .txt in ~/recordings/
```

Flow: model warms once, then each Enter cycles record→transcribe→`pbcopy`. Paste with `⌘V` into any app. Idle RAM: ~600MB while the loop is running.

For a global hotkey (à la SuperWhisper), bind `Fn` or `⌥+Space` in Karabiner-Elements / macOS Shortcuts to send `\n` to the dictate session's stdin. Native daemon-mode with system-wide hotkey is on the v1.1 roadmap.

### Recording

```sh
meeting-record                       # timestamp name, ~/recordings/, defaults
meeting-record team-sync             # custom basename
meeting-record --diarize             # add speaker labels post-meeting
meeting-record --diarize --summary   # +action items / decisions via gemma4
meeting-record --no-browser          # skip auto-open of live page
meeting-record --polish              # EXPERIMENTAL streaming LLM polish (off by default)
meeting-record --list-devices        # list mics + system-audio hint
meeting-record --device ":2"         # pick a non-default device
meeting-record --from-file f.wav     # transcribe an existing file (no mic)
```

Ctrl-C once = clean stop. Ctrl-C twice = hard exit (everything still flushed). Or use the **stop** button in the live page (no terminal needed).

### Subcommands (post-meeting tooling)

```sh
meeting-record redo  ~/recordings/<name>.flac          # re-run offline pass
meeting-record diarize ~/recordings/<name>.flac        # speaker labels
meeting-record summary ~/recordings/<name>.offline.md  # gemma4 summary
meeting-record polish  ~/recordings/<name>.offline.md  # gemma4 cleanup
meeting-record search "V5 environment"                 # FTS5 across all meetings
meeting-record search --reindex                        # rebuild the index
meeting-record record search                           # record a meeting NAMED "search"
```

## Outputs

In `$MEETING_DIR` (default `~/recordings/`):

| File | Purpose | When |
|---|---|---|
| `<name>.flac` | Audio backup, mono 16k, playable while recording | always |
| `<name>.md` | Live transcript, written during the meeting | always |
| `<name>.txt` | Plain transcript, fsync'd per chunk | always |
| `<name>.log` | ffmpeg + script stderr | always |
| `<name>.offline.md` | Re-transcribed offline (full attention, more accurate) | unless `--no-offline-pass` |
| `<name>.offline.txt` | Plain offline transcript with paragraph breaks on silence | with offline pass |
| `<name>.offline.json` | Per-sentence timestamps + duration | with offline pass |
| `<name>.diarized.md` | Speaker-labeled transcript | with `--diarize` |
| `<name>.diarized.json` | Speaker spans + per-sentence speaker labels | with `--diarize` |
| `<name>.summary.md` | 3-section structured summary (decisions / actions / open Q's) | with `--summary` |

The streaming live `.md` is the page-of-record during the meeting. The `.offline.md` is markedly more accurate (full-attention chunked transcribe; in our tests `Cross Camp` → `Chris Kemp`, `non-Jeb ins` → `non Jeff admins`) and is what to share afterward.

## Live page

A localhost page opens automatically. SSE-driven: no polling, auto-reconnects, snapshot on connect (so refresh and second tabs work).

The header shows: meeting name, started time, audio + wall durations, input device, polish status (when on), and a `live`/`reconnecting`/`stopped` connection indicator. The status pill pulses while recording and includes a 9-bar peak-dB meter for the mic — silence reads as silence, normal speech lights ~5 bars green, clipping flashes red.

Below the header: a collapsible **markers** TOC listing every 5-min timestamp + user marks (★), each clicking-back to its position in the transcript. Sticky file paths underneath so you always know where the artifacts are landing.

### Operator controls

| Key | Button | Action |
|---|---|---|
| `C` | copy | full transcript to clipboard |
| `M` | mark | insert a `★` timestamp at this moment |
| `/` | find | in-page search; `Enter` / `Shift+Enter` cycle, `Esc` closes |
| `?` | help (`?`) | keyboard shortcut overlay |
| `J` | (floating pill) | jump to the live tail |
| `R` | raw | toggle raw/polished view (only shown when `--polish` is on) |
| `S` | stop | graceful shutdown (confirmation modal) |
| `Esc` | — | close find / help / dialog |

### Visual design

Typography: warm-paper light + cream-on-near-black dark, optical sizing, 68ch measure, 5-min timestamps as section rules. Mobile breakpoint at 640px. Binds to `127.0.0.1` only.

WCAG AA contrast on all text including streaming draft. `prefers-reduced-motion` respected.

## Chat about it in Claude Code

The `.md` files are written atomically; reference any of them mid-meeting or after:

```
@~/recordings/team-sync.md           # live transcript (current chunk)
@~/recordings/team-sync.offline.md   # accurate post-meeting transcript
@~/recordings/team-sync.diarized.md  # speaker-labeled
@~/recordings/team-sync.summary.md   # structured summary
```

## System audio (Zoom/Meet)

The default mic-only setup misses remote participants. With BlackHole installed:

1. `brew install --cask blackhole-2ch` (requires reboot)
2. Open Audio MIDI Setup, create an Aggregate Device combining BlackHole + your mic
3. Set a Multi-Output Device (BlackHole + speakers) as system output during the meeting
4. `meeting-record --device ':<aggregate-index>' team-sync`

`meeting-record --list-devices` detects BlackHole and prints the right index.

## Crash safety

- ffmpeg writes FLAC with `-flush_packets 1` so `kill -9` leaves a playable file
- Transcript file is `O_APPEND` and fsynced per finalized-token batch (~2s)
- `.md` is rewritten via `write → fsync → rename` (atomic; readers never see torn content)
- Diarization falls back to `ffmpeg`-decode if soundfile can't read a partial FLAC
- Ctrl-C is caught: ffmpeg drains, transcript flushes, page shows "stopped"

## Environment

| Var | Default | Notes |
|---|---|---|
| `MEETING_DIR` | `~/recordings` | Output directory |
| `MEETING_DEVICE` | `:0` | avfoundation audio device |
| `MEETING_PORT` | `0` | HTTP port (0 = ephemeral) |
| `PARAKEET_MODEL` | `mlx-community/parakeet-tdt-0.6b-v3` | parakeet-mlx HF repo |
| `MEETING_POLISH_MODEL` | `gemma4:e2b` | streaming polish model |
| `MEETING_SUMMARY_MODEL` | `gemma4:latest` | summary model |
| `MEETING_GLOSSARY` | `~/recordings/.glossary.txt` | one named-entity per line for polish |

## Tradeoffs

- 16kHz mono FLAC. Good enough for speech; ~10MB/hour. Higher quality available with `--device` pointing at a 48k aggregate.
- Diarization clustering threshold (default 0.65) tuned for compressed VoIP. Pristine broadcast audio merges similar voices at this threshold; bump to `--diarize-threshold 0.7` if speakers are over-split.
- Summary model occasionally invents dates not in transcript. Spot-check before sharing.
- Streaming polish (`--polish`) is opt-in; ordering bugs surface on long sessions.

## Eval-driven defaults

The streaming-mode `depth=8` default came from a real eval sweep (`evals/run_eval.py`, sweep-2026-05-06.md). On a 2-min real-meeting clip vs frozen-offline ground truth:

| Config | Live WER |
|---|---|
| ctx=256 d=1 (parakeet's default) | 19.3% |
| ctx=256 **d=8** (our default) | **13.4%** |
| ctx=256 d=12 | 13.4% (saturates) |
| ctx=256 d=1 keep_orig=1 | 36.5% (broken) |

`depth=N` controls how many encoder layers preserve exact non-streaming computation. depth=8 is the inflection point on parakeet-tdt-0.6b-v3; same wall time as depth=1, ~31% relative WER improvement.

Tune via env vars without rebuilding:
```sh
MEETING_STREAM_DEPTH=12 recorder team-sync           # try a different depth
MEETING_CONTEXT_SIZE=512 recorder team-sync          # widen attention
MEETING_KEEP_ORIGINAL_ATTENTION=1 recorder team-sync # full attention (slow + worse for streaming)
```

Run your own eval after a real meeting:
```sh
# 1. Make a frozen reference from the offline pass
cp ~/recordings/<name>.offline.txt ~/recordings/<name>.offline-frozen.txt
# 2. Add to evals/meeting-corpus.toml
# 3. Sweep configs
for d in 1 4 8; do
  MEETING_STREAM_DEPTH=$d evals/run_eval.py --label "d$d" \
    --corpus evals/meeting-corpus.toml --clip <id>
done
# 4. Read evals/sweep-YYYY-MM-DD.md
```

After every recording, the script prints a one-line quality estimate comparing live vs offline (Levenshtein-style word-diff via stdlib `difflib`). Trust signal at no extra cost.

### Other eval modes

`run_eval.py` supports three additional modes beyond raw WER:

```sh
# Hallucination check: flag proper nouns/dates in summary not in source
evals/run_eval.py --mode hallucination \
  --source ~/recordings/meeting.offline.txt \
  --summary ~/recordings/meeting.summary.md

# Search recall: inject distinctive 4-word phrases, query, measure hit rate
evals/run_eval.py --mode search-recall

# Polish A/B: run gemma4 polish on a transcript, compare WER + entity drop rate
evals/run_eval.py --mode polish-ab --source ~/recordings/meeting.offline.txt
```

**Findings from the actual evals so far** (sweep-2026-05-0[67].md):

- **Streaming WER on a real meeting**: avg 14.2% live, 12.6% offline across 4 different 2-min slices of the same meeting. The earlier "depth=8 → 31% improvement" claim was inflated — single-clip eval masked an offline-pass truncation bug (`chunk_duration=120` was dropping the last 40% of clips that ended near a chunk boundary). After the chunking fix, live and offline converge: gap is ~10pp, not the original 16pp.
- **Eval framework caveats**: WER is computed against a *frozen offline-mode parakeet output*, not a human-verified reference. So "WER" really means "agreement with a max-context parakeet pass." The absolute number is parakeet-vs-parakeet self-consistency, not transcription accuracy in the human sense. The `Live-vs-Off` column compares both transcripts from the same eval pass, eliminating frozen-ref drift — most honest metric we have today.
- **Eval modes work cross-corpus**: `polish-ab --corpus` and `hallucination --corpus` sweep every clip in one invocation (no shell loop). 4-slice corpus shows polish hurts WER consistently (−1 to −5pp) but reveals different per-slice failure modes (Madison/Mike dropped on one, Hyperforce/Snowflake mis-flagged as "added" on another).
- **Hallucination matcher uses word-boundary regex** (not naive `in`): catches the real `2024-05-22` fabrication while not false-flagging substring matches like `May` in `maybe` or `24` in `2024`. Verb-blacklist removes false-positives from action-item bullets.
- **Summary hallucination**: gemma4:e2b summary fabricated `(by 2024-05-22)` on a real meeting — the eval flagged it.
- **Polish A/B**: post-meeting `recorder polish` HURT WER by 4.6pp on a proper-noun-heavy clip even after prompt tightening; entity preservation 90% (was 70% before tightening). **Use polish with caution on transcripts that include numbers, times, and proper nouns** — review before sharing.
- **Diarize stability**: 100% boundary IoU between consecutive runs (proves determinism on identical input; doesn't measure robustness to noise/threshold).
