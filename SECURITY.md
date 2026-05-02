# Security Policy

DM-Code-Agent can execute local file, Python, shell, and MCP tools. Treat it as a
developer automation tool, not as a sandbox.

## Supported versions

The `main` branch is the actively supported development version.

## Reporting a vulnerability

Please open a private report if GitHub security advisories are enabled, or create an issue
with a minimal reproduction that avoids exposing secrets.

## Safety notes

- Never commit `.env`, API keys, `config.json`, or `mcp_config.json`.
- Review commands before allowing the agent to run on sensitive repositories.
- Use isolated test workspaces for untrusted tasks.
- Disable MCP servers you do not need.
