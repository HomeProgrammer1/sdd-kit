# EXAMPLE-001: Technical plan

Spec: ./spec.md · Status: Approved (2026-10-16)

## 1. Approach
Follows the existing email-verification flow (token table + mailer job).

## 2. Components and changes
| Component | Change |
|---|---|
| `password_reset_tokens` table | new: user_id, token_hash, expires_at, used_at |
| `POST /auth/password-reset` | new: request link (rate limited) |
| `POST /auth/password-reset/confirm` | new: set password, revoke sessions |
| `/forgot-password`, `/reset-password` pages | new, reuse `AuthForm` component |

## 3. Data
Migration adds the table; rollback drops it. No backfill.

## 4. Interfaces
`POST /auth/password-reset {email}` → 202 always. `POST /auth/password-reset/confirm {token, password}` → 204 | 410 expired/used | 422 weak password.

## 5. Dependencies
None new.

## 6. Testing strategy
Unit: token service (expiry, single use, hashing). Integration: endpoints with real DB in a container. E2E: AC-1, AC-3, AC-4 in Playwright.

## 7. Risks and rollout
| Risk | Mitigation |
|---|---|
| Email abuse | NFR-1 rate limit + same response |
Rollout behind flag `password_reset`. Rollback: flag off.

## 8. ADRs
none
