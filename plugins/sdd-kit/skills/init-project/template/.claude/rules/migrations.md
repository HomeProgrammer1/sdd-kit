---
paths:
  - "**/migrations/**"
  - "**/migrate/**"
  - "**/*.sql"
---
# Migration rules
- Every migration has a tested rollback (or a written reason why not in the plan).
- Zero-downtime: expand → migrate data → contract, in separate releases.
- Test on seeded data that includes the conflicting shapes, not only on an empty DB.
