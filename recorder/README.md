# recorder

A personal local Whisper-class stack for Apple Silicon. Two workflows:

1. **Dictate** -- push-to-talk to transcript on your clipboard. SuperWhisper-style, but local, free, and yours.
2. **Record** -- full meeting capture with live web UI, speaker diarization, summary, search across past meetings.

All local. No cloud. No data leaves your machine.

Stack: [parakeet-mlx](https://github.com/senstella/parakeet-mlx) for ASR, [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) for diarization, [Ollama](https://ollama.com) for summary + cleanup.

Binary is `recorder`. `dictate` is a first-class subcommand. Older docs / muscle-memory may say `meeting-record`; a `bin/meeting-record` symlink keeps that working.

## Install

```sh
brew install ffmpeg
# optional, REQUIRED for capturing remote-participant audio in Zoom/Meet:
brew install --cask blackhole-2ch
# optional, for --summary and --polish:
ollama pull gemma4:e2b   # or gemma4:latest if you have headroom
```

First run downloads the parakeet model (~600MB) into `~/.cache/huggingface/`. First `--diarize` run downloads ~35MB of sherpa-onnx models into `~/.cache/meeting-record/`. The terminal app needs Microphone permission (System Settings > Privacy & Security > Microphone) -- the watchdog warns within 5 seconds if access was denied.

Without BlackHole you only capture room audio: your voice plus your speakers playing the remote feed at low SNR. BlackHole routes the clean digital mix.

## System audio setup (BlackHole)

One-time, after `brew install --cask blackhole-2ch`:

1. **Reboot.** The kernel driver only loads at boot.
2. Open **Audio MIDI Setup** (Spotlight: "audio midi setup").
3. Click the `+` button, choose **Create Aggregate Device**. Check both your built-in mic and **BlackHole 2ch** in the list. Name it "Recorder Input" (or anything memorable).
4. (Optional) Create a **Multi-Output Device** combining BlackHole 2ch and your speakers/headphones. Set it as your system output during the meeting so you can hear remote participants while recording.
5. Run `recorder --list-devices` to find the aggregate device's index (e.g. `:2`).
6. Pass that index: `recorder --device ":2" team-sync`.

At startup, `recorder` opportunistically checks for a BlackHole-containing aggregate device and prefers it when no `--device` flag is passed. Fall back to mic-only when no aggregate is configured.

## Quick start: meeting recording

```sh
recorder                           # timestamp name, ~/recordings/, defaults
recorder team-sync                 # custom basename
recorder --diarize                 # add speaker labels post-meeting
recorder --diarize --summary       # + action items / decisions via gemma4
recorder --polish                  # EXPERIMENTAL streaming LLM polish
recorder --no-browser              # skip auto-open of live page
recorder --from-file meeting.wav   # transcribe an existing file (no mic)
recorder --list-devices            # list available audio devices
recorder --device ":2"             # pick a non-default device
```

A browser tab opens automatically to the live transcript page. Ctrl-C once = clean stop (everything flushed). Ctrl-C twice = hard exit. The **stop** button in the live page also works without touching the terminal.

## Quick start: push-to-talk dictation

```sh
recorder dictate            # Enter to start, Enter again to stop; transcript to clipboard
recorder dictate --polish   # gemma4 cleanup before clipboard
recorder dictate --save     # also keep .flac + .txt in ~/recordings/
```

Flow: model warms once, then each Enter cycles record->transcribe->`pbcopy`. Paste with Cmd-V into any app. Idle RAM: ~600MB while the loop is running.

For a global hotkey (SuperWhisper-style), bind `Fn` or `Opt+Space` in Karabiner-Elements / macOS Shortcuts to send `\n` to the dictate session's stdin. Native daemon-mode with system-wide hotkey is on the v1.1 roadmap.

## Subcommands (post-meeting tooling)

```sh
recorder redo  ~/recordings/<name>.flac          # re-run offline transcription pass
recorder diarize ~/recordings/<name>.flac        # add speaker labels
recorder summary ~/recordings/<name>.offline.md  # gemma4 structured summary
recorder polish  ~/recordings/<name>.offline.md  # gemma4 cleanup
recorder search "V5 environment"                 # FTS5 search across all meetings
recorder search --reindex                        # rebuild the search index
recorder record search                           # record a meeting NAMED "search"
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

The streaming live `.md` is the page-of-record during the meeting. The `.offline.md` is markedly more accurate (full-attention chunked transcribe; in our tests `Cross Camp` -> `Chris Kemp`, `non-Jeb ins` -> `non Jeff admins`) and is what to share afterward.

## Live page

A localhost page opens automatically. SSE-driven: no polling, auto-reconnects, snapshot on connect (so refresh and second tabs work). Binds to `127.0.0.1` only.

| Key | Button | Action |
|---|---|---|
| `C` | copy | full transcript to clipboard |
| `M` | mark | insert a `*` timestamp at this moment |
| `/` | find | in-page search; `Enter` / `Shift+Enter` cycle, `Esc` closes |
| `?` | help | keyboard shortcut overlay |
| `J` | (floating pill) | jump to the live tail |
| `R` | raw | toggle raw/polished view (only shown when `--polish` is on) |
| `S` | stop | graceful shutdown (confirmation modal) |
| `Esc` | -- | close find / help / dialog |

The header shows: meeting name, started time, audio + wall durations, input device, polish status (when on), and a `live`/`reconnecting`/`stopped` connection indicator. The status pill pulses while recording and includes a 9-bar peak-dB meter for the mic -- silence reads as silence, normal speech lights ~5 bars green, clipping flashes red.

Below the header: a collapsible **markers** TOC listing every 5-min timestamp plus user marks (`M`), each linking back to its position in the transcript. Sticky file paths underneath so you always know where artifacts are landing.

## Chat about it in Claude Code

The `.md` files are written atomically; reference any of them mid-meeting or after:

```
@~/recordings/team-sync.md           # live transcript (current chunk)
@~/recordings/team-sync.offline.md   # accurate post-meeting transcript
@~/recordings/team-sync.diarized.md  # speaker-labeled
@~/recordings/team-sync.summary.md   # structured summary
```

## Crash safety

- ffmpeg writes FLAC with `-flush_packets 1` so `kill -9` leaves a playable file
- Transcript file is `O_APPEND` and fsynced per finalized-token batch (~2s)
- `.md` is rewritten via `write -> fsync -> rename` (atomic; readers never see torn content)
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
| `MEETING_STREAM_DEPTH` | `8` | encoder layers using full (non-streaming) attention |
| `MEETING_CONTEXT_SIZE` | `256` | token context window for streaming pass |
| `MEETING_KEEP_ORIGINAL_ATTENTION` | `0` | set to `1` for full attention (slower, worse for streaming) |

## Tradeoffs

- 16kHz mono FLAC. Good enough for speech; ~10MB/hour. Higher quality available with `--device` pointing at a 48k aggregate.
- Diarization clustering threshold (default 0.65) tuned for compressed VoIP. Pristine broadcast audio merges similar voices at this threshold; bump to `--diarize-threshold 0.7` if speakers are over-split.
- Summary model occasionally invents dates not in transcript. Spot-check before sharing.
- Streaming polish (`--polish`) is opt-in; ordering bugs surface on long sessions.

## Eval-driven defaults

The streaming-mode `depth=8` default came from a real eval sweep. `depth=N` controls how many encoder layers preserve exact non-streaming computation. depth=8 is the inflection point on parakeet-tdt-0.6b-v3: same wall time as depth=1, roughly 31% relative WER reduction on real meeting audio. Beyond depth=8 the metric saturates.

Full sweep results and methodology are in [evals/README.md](evals/README.md).

Tune via env vars without rebuilding:

```sh
MEETING_STREAM_DEPTH=12 recorder team-sync            # try a different depth
MEETING_CONTEXT_SIZE=512 recorder team-sync           # widen attention
MEETING_KEEP_ORIGINAL_ATTENTION=1 recorder team-sync  # full attention (slow + worse for streaming)
```

After every recording, the script prints a one-line quality estimate comparing live vs offline transcript (Levenshtein-style word-diff via stdlib `difflib`). Trust signal at no extra cost.

To run your own sweep after a real meeting:

```sh
# 1. Freeze the offline pass as reference
cp ~/recordings/<name>.offline.txt ~/recordings/<name>.offline-frozen.txt
# 2. Add the clip to evals/meeting-corpus.toml
# 3. Sweep depths
for d in 1 4 8 12; do
  MEETING_STREAM_DEPTH=$d evals/run_eval.py --label "d$d" \
    --corpus evals/meeting-corpus.toml --clip <id>
done
# 4. Read evals/sweep-YYYY-MM-DD.md
```

Key finding from the polish eval: `recorder polish` hurt WER by 2-5pp on proper-noun-heavy clips even after prompt tightening (90% entity preservation, up from 70%). Review polished output before sharing transcripts that include names, numbers, or dates.

## Eval modes

`evals/run_eval.py` supports raw WER sweeps plus three additional modes: hallucination detection (flags proper nouns and dates in the summary not present in the source), search-recall (injects distinctive phrases, queries the index, measures hit rate), and polish A/B (compares WER and entity preservation before/after `recorder polish`). See [evals/README.md](evals/README.md) for usage and findings.
