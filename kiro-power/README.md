<!--
Kiro powers format: https://kiro.dev/docs/powers/create/ (manifest plugin.json, optional mcp.json and skills/)
Install: https://kiro.dev/docs/powers/ (Add Custom Power, then Import power from a folder or from GitHub).
The power follows the Agent Plugins specification: https://agent-plugins.org
-->

# ARGUS Kiro power

One install gives Kiro the ARGUS MCP server (started with `uvx` from the GitHub repository) and the
working guide as a skill.

## Install

1. Install `uv` (https://docs.astral.sh/uv/) and `ffmpeg`. Install Node.js 18 or newer for the graphics engine.
2. In Kiro, open the Powers panel, choose Add Custom Power, then import this folder (`kiro-power/`)
   from a clone of https://github.com/vertovhq/argus. Importing from the GitHub URL is possible too; the
   folder must then be the power root.
3. Wait for the first start to install the graphics engine (about a few minutes). The `doctor` tool, or
   `uvx --from git+https://github.com/vertovhq/argus argus-doctor` in a terminal, shows the `engine` line
   as ok when it is ready.

Keys (optional) go in `~/.argus/.env`. Outputs go to `./output` unless `OMNIFRAME_OUTPUT_DIR` is set; the
power's `mcp.json` does not set it.
