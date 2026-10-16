---
paths:
  - "**/*.test.*"
  - "**/*.spec.*"
  - "**/*_test.*"
  - "**/test_*.py"
  - "**/tests/**"
  - "**/__tests__/**"
  - "**/*Tests.swift"
  - "**/src/test/**"
  - "**/src/androidTest/**"
  - "**/integration_test/**"
---
# Test file rules
- Never add skip/only/xfail/@Ignore to make a run pass.
- Never loosen an assertion or update a snapshot without reading the diff.
- Name tests after behaviour; reference the AC ID in the name or a comment.
- No real network, clock or randomness in unit tests.
