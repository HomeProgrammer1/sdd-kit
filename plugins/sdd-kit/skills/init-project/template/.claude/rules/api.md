---
paths:
  - "src/api/**"
  - "**/routes/**"
  - "**/controllers/**"
  - "**/handlers/**"
  - "**/*.proto"
  - "**/openapi*.{yml,yaml,json}"
---
# API rules
- Contract change first (OpenAPI/proto/schema), then code.
- Every endpoint: input validation, authz check, standard error shape, test for 401/403/422.
- Breaking changes need a new version or an explicit decision in the plan.
