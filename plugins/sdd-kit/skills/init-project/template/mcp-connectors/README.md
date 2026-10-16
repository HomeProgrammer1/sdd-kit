# Connector snippets (optional)

Merge the servers you need into the root `.mcp.json` under `mcpServers`.
Tokens are never written into files: each snippet reads them from environment
variables (`${VAR}`), set in your shell or a secrets manager.

Rules of thumb:
1. **Least privilege at the server**: use the server's allow/deny list
   (`ENABLED_TOOLS`, `*_DENIED_TOOLS_REGEX`, read-only modes) so dangerous
   tools never exist for the model. That is stronger than any prompt.
2. **Pin versions** (`package@x.y.z`) once a connector works; `@latest` can change under you.
3. Endpoints and package names change: check each vendor's current MCP docs before use.
4. Claude Code asks you to approve project servers from `.mcp.json` the first time.

| File | For | Notes |
|---|---|---|
| github.json | Issues, PRs | Remote server, needs a fine-grained PAT |
| gitlab.json | MRs, pipelines (incl. self-hosted) | Community server; deny merge/delete tools |
| atlassian.json | Jira + Confluence (Server/DC or Cloud) | Community server; allowlist tools |
| linear.json | Linear issues | Remote server, OAuth on first use |
| figma.json | Design context for UI work | Remote server, OAuth on first use |
| playwright.json | Browser automation for the verifier | Local, no credentials |
