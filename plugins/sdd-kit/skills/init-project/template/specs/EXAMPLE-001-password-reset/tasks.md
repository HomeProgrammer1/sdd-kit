# EXAMPLE-001: Tasks

- [ ] T-1 Add password_reset_tokens migration and model — ACs: AC-3, AC-4 — verify: migration up/down test
- [ ] T-2 Token service: issue, hash, validate, consume — ACs: AC-3, AC-4 — verify: unit tests
- [ ] T-3 POST /auth/password-reset with rate limit — ACs: AC-1, AC-2 — verify: integration tests
- [ ] T-4 POST /auth/password-reset/confirm + revoke sessions — ACs: AC-4, AC-5 — verify: integration tests
- [ ] T-5 [P] /forgot-password page — ACs: AC-1, AC-2 — verify: component test + e2e
- [ ] T-6 [P] /reset-password page — ACs: AC-3, AC-4 — verify: component test + e2e
- [ ] T-7 Update README and CHANGELOG — ACs: n/a — verify: review

## Traceability
| AC | Tasks |
|---|---|
| AC-1 | T-3, T-5 |
| AC-2 | T-3, T-5 |
| AC-3 | T-1, T-2, T-6 |
| AC-4 | T-1, T-2, T-4, T-6 |
| AC-5 | T-4 |
