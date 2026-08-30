# Onboard another game

The reusable boundary is the canonical `users` + `events` adapter, not NewtonMarket-specific event names.

## 1. Map data

Create read-only views that satisfy `config/schema_contract.json`. Keep original warehouse tables untouched. If a title has accounts, characters, and devices, decide which one is the metric entity and document it.

## 2. Register metrics

Add definitions to `config/metrics.json`. Supported deterministic kinds are:

- `retention`;
- `distinct_user_conversion`;
- `event_count_per_user`;
- `duplicate_signature_rate`.

Each definition carries its formula, unit, grain, owner, source, and quality notes. Add a new engine strategy rather than embedding raw SQL in prompts when a new metric kind is needed.

## 3. Configure investigation playbooks

Add an alert metric, current/baseline windows, shared filters, breakdown dimension, related metrics, and evidence queries to `config/scenarios.json`. Keep ground truth outside public config.

## 4. Validate

Add metric-contract, SQL-policy, tool-routing, incident-attribution, and governance cases. Run tests and the fixed eval suite. Measure Claude latency and cost only after an authenticated run.

## 5. Productionize

Swap SQLite for a warehouse adapter behind the same tool functions. Preserve read-only credentials, query timeouts, cost limits, result sampling, evidence hashes, and human approval.

