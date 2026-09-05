import pytest
from app.services.confidence import criterion_confidence, overall_confidence


class TestCriterionConfidence:
    def test_fully_satisfied(self):
        assert criterion_confidence(50.0, 100.0, 20.0) == 1.0

    def test_exactly_at_threshold(self):
        assert criterion_confidence(100.0, 100.0, 20.0) == 1.0

    def test_fully_failed(self):
        assert criterion_confidence(125.0, 100.0, 20.0) == 0.0

    def test_exactly_at_tolerance_boundary(self):
        assert criterion_confidence(120.0, 100.0, 20.0) == 0.0

    def test_midpoint_linear_decay(self):
        # halfway between threshold (100) and threshold+tolerance (120) → 0.5
        result = criterion_confidence(110.0, 100.0, 20.0)
        assert abs(result - 0.5) < 1e-9

    def test_quarter_decay(self):
        # 5 km past threshold of 100 with tolerance 20 → 1 - 5/20 = 0.75
        result = criterion_confidence(105.0, 100.0, 20.0)
        assert abs(result - 0.75) < 1e-9

    def test_zero_tolerance_pass(self):
        assert criterion_confidence(99.9, 100.0, 0.0) == 1.0

    def test_zero_tolerance_fail(self):
        assert criterion_confidence(100.1, 100.0, 0.0) == 0.0

    def test_negative_tolerance_treated_as_zero(self):
        assert criterion_confidence(99.0, 100.0, -5.0) == 1.0
        assert criterion_confidence(101.0, 100.0, -5.0) == 0.0


class TestOverallConfidence:
    def test_empty_scores(self):
        assert overall_confidence({}) == 0.0

    def test_min_mode_single(self):
        assert overall_confidence({"a": 0.8}, mode="min") == 0.8

    def test_min_mode_weakest_link(self):
        scores = {"a": 1.0, "b": 0.5, "c": 0.9}
        assert overall_confidence(scores, mode="min") == 0.5

    def test_weighted_avg_uniform(self):
        scores = {"a": 0.8, "b": 0.4}
        result = overall_confidence(scores, mode="weighted_avg")
        assert abs(result - 0.6) < 1e-9

    def test_weighted_avg_with_weights(self):
        scores = {"a": 1.0, "b": 0.0}
        # weight a=3, b=1 → (3*1.0 + 1*0.0) / 4 = 0.75
        result = overall_confidence(scores, mode="weighted_avg", weights={"a": 3.0, "b": 1.0})
        assert abs(result - 0.75) < 1e-9

    def test_weighted_avg_missing_weight_defaults_to_1(self):
        scores = {"a": 1.0, "b": 0.0}
        # weight a=2, b missing → defaults to 1 → (2*1.0 + 1*0.0) / 3
        result = overall_confidence(scores, mode="weighted_avg", weights={"a": 2.0})
        assert abs(result - 2.0 / 3.0) < 1e-9

    def test_all_perfect(self):
        scores = {"a": 1.0, "b": 1.0, "c": 1.0}
        assert overall_confidence(scores, mode="min") == 1.0
        assert overall_confidence(scores, mode="weighted_avg") == 1.0
