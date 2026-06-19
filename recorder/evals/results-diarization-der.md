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

## Threshold sweep: tuning does NOT fix it

| threshold | detected speakers | DER |
|---|---|---|
| 0.65 (default) | 19 | 70.0% |
| 0.75 | 14 | 68.6% |
| 0.85 | 8 | 68.5% |
| 0.90 | 7 | 67.5% |

Driving the cluster count from 19 down to 7 (nearly the true 4) moves DER by
only 2.5 points. The DER curve is flat-and-catastrophic across thresholds, so
over-clustering is a symptom, not the disease.

Timeline sanity-check (IS1009a) confirms the failure is speaker *confusion*,
not missed/false-alarm speech: hypothesis and reference share the same
max_end (805.7s) and similar total speech (hyp 693.5s vs ref 722.4s), and the
reference has almost no overlap (0.90 speech/wall ratio). So the diarizer
places speech in roughly the right time slots but assigns the wrong speaker
identity. The 3D-Speaker CAMPPlus embeddings do not separate these 4 AMI
speakers on 16kHz mixed-headset audio, which no clustering threshold can
recover.

Conclusion: diarization quality on meeting audio is a model/embedding problem,
not a tuning problem. Threshold tuning is off the table. Real options are a
different embedding model, a different diarizer (e.g. pyannote.audio end-to-end
rather than sherpa-onnx's segment-then-cluster), or accepting that speaker
labels are unreliable and presenting them with a caveat.

## How to reproduce

```sh
bash evals/fetch_ami.sh          # one-time: download 3 AMI meetings + RTTM
uv run evals/run_eval.py --mode diarize-der --corpus evals/ami-corpus.toml
# sweep a threshold:
uv run evals/run_eval.py --mode diarize-der --corpus evals/ami-corpus.toml --threshold 0.85
```
