# EXAMPLE-001: Password reset by email

| Field | Value |
|---|---|
| Status | Approved (2026-10-16, product owner) |
| Source | verbal request, 2026-10-16 |
| Profile | web + backend |

## 1. Problem and goal
Users who forget their password open a support ticket today (about 40 tickets a week). After this ships, a user resets the password themselves from the login page in under two minutes, without support.

## 2. Users and scenarios
- Registered user, logged out: "Forgot password?" → enters email → receives link → sets new password → logged in.

## 3. Functional requirements
- **FR-1** The system shall let a logged-out user request a reset link by email address.
- **FR-2** When a reset is requested, the system shall email a single-use link valid for 30 minutes.
- **FR-3** If the link is expired or already used, then the system shall refuse it and offer to send a new one.
- **FR-4** When a new password is set, the system shall end all of that user's other sessions.

## 4. Acceptance criteria
- **AC-1** (FR-1) Given a registered email, When the user submits it on /forgot-password, Then the page shows "If this email exists, we sent a link" and one email is queued.
- **AC-2** (FR-1) Given an unregistered email, When submitted, Then the page shows the same message and no email is queued.
- **AC-3** (FR-2) Given a link issued 29 minutes ago and unused, When opened, Then the "Set new password" form is shown.
- **AC-4** (FR-3) Given a link issued 31 minutes ago, When opened, Then the page shows "Link expired" with a "Send a new link" button.
- **AC-5** (FR-4) Given the user is logged in on two devices, When they set a new password on a third, Then both other sessions are logged out on their next request.

## 5. Non-functional requirements
- **NFR-1** Security: at most 5 reset requests per email per hour; tokens stored hashed.
- **NFR-2** Accessibility: both forms meet WCAG 2.2 AA.

## 6. Out of scope
- Reset by SMS; changing email address; password strength meter redesign.

## 7. Decisions
| # | Decision | Source | Date |
|---|---|---|---|
| 1 | Same message for known and unknown emails (no account enumeration) | human | 2026-10-16 |

## 8. Open questions
- none
