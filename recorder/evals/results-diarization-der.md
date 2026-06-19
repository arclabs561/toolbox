# Diarization DER baseline (AMI ground truth)

Diarization error rate of the recorder pipeline (sherpa-onnx pyannote
segmentation + 3D-Speaker CAMPPlus embeddings + FastClustering) measured
against the AMI Meeting Corpus human RTTM references. AMI meetings are
4-speaker; DER is computed by `evals/run_eval.py --mode diarize-der` via
pyannote.metrics (NIST collar 0.25s).

Lower DER is better. State-of-the-art systems score ~5-15% on AMI. A DER of
~70% with 19 detected speakers (vs 4 true) is the over-clustering failure this
calibration exists to fix.

## Baseline: default clustering (threshold 0.65, num_clusters=-1)

| clip | true speakers | detected | DER |
|---|---|---|---|
| AMI-IS1009a | 4 | 19 | 70.0% |

The detected-speaker count (19 vs 4) is the headline: the FastClustering auto
mode at threshold 0.65 fragments 4 real voices into 19 clusters, and the DER
reflects the resulting speaker-confusion. Threshold sweep on a separate meeting
showed the count is threshold-driven (0.45 -> 40, 0.55 -> 26, 0.65 -> 18,
0.75 -> 13 clusters), but cluster count alone is not the metric -- the next
step is to sweep threshold (and num_clusters / min_duration knobs) against DER
on this corpus and keep whatever lowers DER, not whatever lands the count
near 4.

## How to reproduce

```sh
bash evals/fetch_ami.sh          # one-time: download 3 AMI meetings + RTTM
uv run evals/run_eval.py --mode diarize-der --corpus evals/ami-corpus.toml
# sweep a threshold:
uv run evals/run_eval.py --mode diarize-der --corpus evals/ami-corpus.toml --threshold 0.85
```
