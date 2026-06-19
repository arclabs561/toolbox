#!/usr/bin/env bash
# Fetch the 3 AMI meetings used by ami-corpus.toml for diarization DER.
#
# Downloads the Mix-Headset track for 3 four-speaker meetings, downconverts to
# 16kHz mono FLAC (matching the recorder pipeline), and copies the matching
# human-labeled RTTM from pyannote/AMI-diarization-setup. ~40MB on disk.
#
# AMI Meeting Corpus is CC-BY-4.0. RTTM references are from
# https://github.com/pyannote/AMI-diarization-setup (manual annotations).
set -euo pipefail

DEST="${MEETING_DIR:-$HOME/recordings}/test-corpus/ami"
SETUP_REPO="$DEST/AMI-diarization-setup"
MIRROR="http://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus"
MEETINGS=(ES2002a ES2004a IS1009a)

mkdir -p "$DEST/audio" "$DEST/rttm"

if [ ! -d "$SETUP_REPO" ]; then
  git clone --depth 1 https://github.com/pyannote/AMI-diarization-setup "$SETUP_REPO"
fi

for m in "${MEETINGS[@]}"; do
  if [ ! -f "$DEST/audio/$m.flac" ]; then
    echo "fetching $m ..."
    wget --no-verbose --continue -O "/tmp/$m.wav" \
      "$MIRROR/$m/audio/$m.Mix-Headset.wav"
    ffmpeg -hide_banner -loglevel error -y -i "/tmp/$m.wav" \
      -ac 1 -ar 16000 -c:a flac "$DEST/audio/$m.flac"
    rm -f "/tmp/$m.wav"
  fi
  # RTTM lives under one of the annotation variant dirs; copy the first match.
  find "$SETUP_REPO" -name "$m.rttm" -exec cp {} "$DEST/rttm/$m.rttm" \; -quit
done

echo "done -> $DEST/{audio,rttm}/"
ls -la "$DEST/audio" "$DEST/rttm"
