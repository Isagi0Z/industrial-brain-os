# Suggestions

Improvement opportunities surfaced by the run (3).

1. No logout / sign-out control exists in the authenticated UI — users cannot end a session without clearing storage. Add a logout action (e.g. in the header avatar or Settings).
2. Start the ingestion worker (`celery -A app.worker worker`) or the ib_worker container so uploaded documents are actually indexed and become searchable.
3. Several requested validations (generate work orders, run compliance/RCA/maintenance/lessons analyses through the browser) cannot be exercised because those flows are status scaffolds only. Wiring at least one brain to a real interactive endpoint would make the vertical demonstrable end-to-end.
