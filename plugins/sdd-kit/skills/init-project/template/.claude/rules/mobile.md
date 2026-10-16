---
paths:
  - "**/*.swift"
  - "**/*.{kt,kts}"
  - "**/*.dart"
  - "ios/**"
  - "android/**"
---
# Mobile rules
- No blocking work on the main thread.
- Secrets and tokens only in Keychain / Keystore / secure storage.
- New permission → spec must state rationale text and denial behaviour.
- Never edit signing configs, provisioning profiles or store metadata.
