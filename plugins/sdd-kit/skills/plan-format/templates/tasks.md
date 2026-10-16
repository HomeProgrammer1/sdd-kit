# <ID>: Tasks

Legend: [P] = may run in parallel with other [P] tasks (no shared files)

- [ ] T-1 <title> — ACs: AC-1
  files: <paths>
  steps:
    1. Write test `<name>` in <file> asserting <exact behaviour>
    2. Run `<command>` → expect FAIL: <reason>
    3. Implement <what> in <file>
    4. Run `<command>` → expect PASS
    5. Commit "<type>(<scope>): <summary>"
- [ ] T-n Update docs/README/CHANGELOG — ACs: n/a

## Traceability
| AC | Tasks |
|---|---|
| AC-1 | T-1 |
