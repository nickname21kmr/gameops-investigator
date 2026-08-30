from __future__ import annotations

from gameops_investigator.metrics import MetricEngine


def test_metric_catalog_is_computable():
    engine = MetricEngine()
    for definition in engine.list_definitions():
        rows = engine.compute(definition["metric_id"])
        assert len(rows) == 1
        assert rows[0].denominator >= 0


def test_player_funnel_is_monotonic():
    engine = MetricEngine()
    tutorial = engine.compute("tutorial_completion_rate")[0]
    trade = engine.compute("trade_success_rate")[0]
    turn_five = engine.compute("turn5_reach_rate")[0]
    assert tutorial.denominator == 5000
    assert tutorial.numerator >= trade.denominator >= trade.numerator >= turn_five.numerator


def test_retention_is_bounded_by_definition():
    engine = MetricEngine()
    for metric_id in ("d1_retention", "d3_retention", "d7_retention"):
        for value in engine.compute(metric_id, group_by=["app_version"]):
            assert value.value is not None
            assert 0 <= value.value <= 100


def test_duplicate_sensitive_and_robust_metrics_diverge():
    engine = MetricEngine()
    filters = {"start_date": "2026-08-08", "end_date": "2026-08-10", "app_version": "0.9.2", "channel": "friend_test"}
    intensity = engine.compute("system_open_events_per_eligible_user", filters=filters)[0]
    adoption = engine.compute("system_adoption_rate", filters=filters)[0]
    duplicate_rate = engine.compute("duplicate_signature_rate", filters=filters)[0]
    assert intensity.value and intensity.value > 1
    assert adoption.value and 0 <= adoption.value <= 100
    assert duplicate_rate.value and duplicate_rate.value > 0

