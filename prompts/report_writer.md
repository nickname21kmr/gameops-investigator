# Evidence-led report prompt

Write for an operations analyst and release owner. Use this order:

1. alert and affected scope;
2. metric definition and statistical method;
3. ranked cause candidates with confidence and evidence IDs;
4. SQL evidence ledger;
5. disconfirmed or unresolved alternatives;
6. next checks, owner, and rollback/decision boundary;
7. limitations and uncertainty.

Every numeric claim must come from a tool result. Every evidence reference must exist in the ledger. Keep the status `human_review_required`.

