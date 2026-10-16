# EXAMPLE-001: Tasks

- [ ] T-1 Token store and service — ACs: AC-3, AC-4
  files: create `migrations/0042_password_reset_tokens.sql`, `src/auth/resetTokens.ts`, `src/auth/resetTokens.test.ts`
  steps:
    1. Write tests `issues_token_valid_for_30_minutes`, `rejects_token_after_30_minutes`, `rejects_used_token`, `stores_only_sha256_hash`
    2. Run `npm test -- resetTokens` → expect FAIL: module not found
    3. Add the migration (table `password_reset_tokens`: id, user_id, token_hash, expires_at, used_at) with a down migration; implement `issue(userId)`, `consume(token)`
    4. Run `npm test -- resetTokens` and `npm run migrate:test -- --up --down` → expect PASS
    5. Commit "feat(auth): password reset token store"
- [ ] T-2 Request endpoint with rate limit — ACs: AC-1, AC-2
  files: `src/auth/routes/passwordReset.ts`, `src/auth/routes/passwordReset.test.ts`
  steps:
    1. Write tests `known_email_queues_one_email`, `unknown_email_queues_nothing_same_response`, `sixth_request_in_an_hour_is_429`
    2. Run → expect FAIL: 404
    3. Implement `POST /auth/password-reset` → always 202; limit 5 per email per hour
    4. Run → expect PASS
    5. Commit "feat(auth): request password reset"
- [ ] T-3 Confirm endpoint, revoke sessions — ACs: AC-4, AC-5
  files: `src/auth/routes/passwordResetConfirm.ts`, test file
  steps: test 204 / 410 / 422 and session revocation → FAIL → implement → PASS → commit
- [ ] T-4 [P] Forgot-password page — ACs: AC-1, AC-2
  files: `web/pages/forgot-password.tsx`, component test, `e2e/password-reset.spec.ts` (AC-1 case)
  steps: component test + e2e → FAIL → implement with `AuthForm` → PASS → commit
- [ ] T-5 [P] Reset-password page — ACs: AC-3, AC-4
  files: `web/pages/reset-password.tsx`, component test, e2e cases AC-3, AC-4
  steps: tests → FAIL → implement → PASS → commit
- [ ] T-6 Docs: README auth section, CHANGELOG — ACs: n/a

## Traceability
| AC | Tasks |
|---|---|
| AC-1 | T-2, T-4 |
| AC-2 | T-2, T-4 |
| AC-3 | T-1, T-5 |
| AC-4 | T-1, T-3, T-5 |
| AC-5 | T-3 |
