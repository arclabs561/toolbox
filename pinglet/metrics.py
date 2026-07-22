"""Pure statistics and human formatting for pinglet diagnostics."""

import math


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def latency_metrics(samples: list[float], sent: int) -> dict[str, object]:
    """Summarize RTT samples while reporting loss separately from variation."""
    received = len(samples)
    lost = max(0, sent - received)
    mean = sum(samples) / received if received else None
    variance = (
        sum((sample - mean) ** 2 for sample in samples) / (received - 1)
        if received > 1 and mean is not None
        else (0.0 if received == 1 else None)
    )
    ipdv = [right - left for left, right in zip(samples, samples[1:], strict=False)]
    positive_ipdv = [value for value in ipdv if value > 0]
    pdv = [sample - min(samples) for sample in samples] if samples else []
    return {
        "sent": sent,
        "received": received,
        "lost": lost,
        "loss_rate": lost / sent if sent else None,
        "rtt_min_ms": min(samples) if samples else None,
        "rtt_mean_ms": mean,
        "rtt_p50_ms": percentile(samples, 0.50),
        "rtt_p95_ms": percentile(samples, 0.95),
        "rtt_p99_ms": percentile(samples, 0.99),
        "rtt_max_ms": max(samples) if samples else None,
        "rtt_sample_variance_ms2": variance,
        "rtt_sample_stddev_ms": math.sqrt(variance) if variance is not None else None,
        "rtt_ipdv_abs_mean_ms": (sum(abs(value) for value in ipdv) / len(ipdv) if ipdv else None),
        "rtt_ipdv_positive_p95_ms": percentile(positive_ipdv, 0.95),
        "rtt_pdv_p95_ms": percentile(pdv, 0.95),
        "rtt_pdv_max_ms": max(pdv) if pdv else None,
        "rtt_ipdv_pairs": len(ipdv),
    }


def quality_status(metrics: dict[str, object] | None) -> str:
    """Classify latency quality separately from whether a probe replied."""
    if not metrics or metrics.get("received", 0) == 0:
        return "unknown"

    loss_rate = metrics.get("loss_rate")
    p50 = metrics.get("rtt_p50_ms")
    p95 = metrics.get("rtt_p95_ms")
    if not isinstance(p50, (int, float)) or not isinstance(p95, (int, float)):
        return "unknown"
    if isinstance(loss_rate, (int, float)) and loss_rate > 0:
        return "degraded"
    if p95 - p50 >= 20 or (p50 > 0 and p95 / p50 >= 3):
        return "degraded"
    return "pass"


def human_number(value: object, suffix: str = "") -> str:
    if value is None:
        return "?"
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}"


def human_rate(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "?"
    rate = float(value)
    for unit in ("bit/s", "Kbit/s", "Mbit/s", "Gbit/s", "Tbit/s"):
        if rate < 1000 or unit == "Tbit/s":
            return f"{rate:.2f} {unit}"
        rate /= 1000
    return "?"
