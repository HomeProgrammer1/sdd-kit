---
name: stack-mobile
description: Mobile app profile for sdd-kit runs (iOS Swift/SwiftUI, Android Kotlin/Compose, Flutter, React Native/Expo) — spec, plan, implementation and verification specifics. Load when CLAUDE.md Stack profile includes mobile.
user-invocable: false
---

## Spec additions
- Min OS versions (e.g. iOS 16+, Android API 26+), phone vs tablet, orientation.
- Offline and poor-network behaviour; what is cached; conflict rules on reconnect.
- Permissions requested (camera, location, notifications): when, why text, behaviour on denial.
- Accessibility: VoiceOver/TalkBack labels, Dynamic Type / font scaling, 44×44 pt / 48×48 dp touch targets.
- Store constraints: privacy nutrition labels / Data safety form, in-app purchase rules if money is involved.

## Plan additions
- Navigation changes, deep links, app lifecycle (background/foreground, process death on Android).
- Backward compatibility with older app versions still calling the API (API versioning, forced update?).
- Local storage: secrets only in Keychain/Keystore; DB migrations for the on-device store.
- Release: feature flag / remote config so the feature can be turned off without a store release.

## Implementation
- Follow the repo's architecture (MVVM/MVI/Clean, BLoC/Riverpod, Redux) and DI setup.
- No blocking work on the main/UI thread; cancel work on lifecycle end.
- Never hardcode API keys; signing files and store credentials are off-limits (guard hook).

## Verification
- Unit tests for view-models/business logic.
- UI tests: XCUITest / Espresso or Compose UI tests / Flutter integration_test / Detox or Maestro.
- Run on at least one simulator/emulator at min OS and one at latest OS.
- Check: rotation, dark mode, largest font size, airplane mode, permission denied.
- Store builds, TestFlight/Play uploads and release are human steps (blocked by the guard hook).
