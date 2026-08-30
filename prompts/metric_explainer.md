# Metric explanation prompt

Explain the requested metric using only `get_metric_definition` output. Include:

- business purpose;
- numerator and denominator;
- entity and deduplication level;
- cohort/date grain;
- event source;
- owner;
- known inflation, maturity, or sample-size risks.

If any field is absent, label it `unknown`; do not infer a formula from the metric name.

