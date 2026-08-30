# Architecture

```mermaid
flowchart LR
    A[Metric alert or analyst question] --> B{Coordinator}
    B -->|open-ended| C[Claude Code]
    B -->|offline demo/evals| D[Deterministic replay]
    C --> E[MCP stdio server]
    D --> F[Same Python tool functions]
    E --> F
    F --> G[Metric catalog]
    F --> H[Read-only SQL guard]
    F --> I[Cohort comparator]
    F --> J[Statistical detector]
    F --> K[Report + citation validator]
    H --> L[(SQLite synthetic analytics)]
    G --> L
    I --> L
    J --> L
    K --> M[Evidence ledger]
    M --> N[Human-review report]
    F --> O[40-case eval harness]
```

The boundary is intentional: the model plans and explains, while deterministic code owns facts and calculations. Claude Code is replaceable by another MCP host; the data/metric/report contract remains stable.

