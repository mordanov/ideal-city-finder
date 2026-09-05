from typing import Literal


def criterion_confidence(actual_value: float, threshold: float, tolerance: float) -> float:
    """
    1.0  — criterion fully satisfied (actual_value <= threshold)
    0.0  — criterion failed even with tolerance (actual_value >= threshold + tolerance)
    linear decay between threshold and threshold + tolerance
    """
    if tolerance <= 0:
        return 1.0 if actual_value <= threshold else 0.0
    if actual_value <= threshold:
        return 1.0
    if actual_value >= threshold + tolerance:
        return 0.0
    return 1.0 - (actual_value - threshold) / tolerance


def overall_confidence(
    criterion_scores: dict[str, float],
    mode: Literal["min", "weighted_avg"] = "min",
    weights: dict[str, float] | None = None,
) -> float:
    """
    mode="min"          weakest-link: overall = min across all criteria scores
    mode="weighted_avg" weighted average; falls back to uniform weights if weights is None
    """
    if not criterion_scores:
        return 0.0
    scores = list(criterion_scores.values())
    if mode == "min":
        return min(scores)
    # weighted_avg
    if weights:
        total_w = sum(weights.get(k, 1.0) for k in criterion_scores)
        return sum(weights.get(k, 1.0) * v for k, v in criterion_scores.items()) / total_w
    return sum(scores) / len(scores)
