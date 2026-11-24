"""argus-install: add the ARGUS MCP server to the config file of each installed AI IDE.

It asks nothing. It finds the clients that are installed and adds or updates only the
`argus` entry in each one's MCP config. Every other server and field stays as it is.
A backup `<file>.argus-backup` is written before the first change to an existing file.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

SERVER_NAME = "argus"
# Fallback when argus-install does not run from an install that has the argus-studio script
# (for example a bare `python -m argus.install`): start ARGUS from GitHub with uvx.
SERVER_COMMAND = "uvx"
SERVER_ARGS = ["--from", "git+https://github.com/vertovhq/argus", "argus-studio"]


def local_server(scripts_dir: Path | None = None) -> tuple[str, list[str]] | None:
    """The argus-studio script next to this Python (the venv install.ps1 / install.sh made), if any.

    It works offline and from a private clone, so it wins over the uvx fallback.
    """
    folder = Path(sys.executable).parent if scripts_dir is None else scripts_dir
    name = "argus-studio.exe" if sys.platform == "win32" else "argus-studio"
    script = folder / name
    return (str(script.resolve()), []) if script.is_file() else None
ROOT_KEY = "mcpServers"
BACKUP_SUFFIX = ".argus-backup"
# A stdio entry cannot carry these, so an old remote entry loses them on update.
REMOTE_ONLY_KEYS = ("url", "serverUrl")


@dataclass(frozen=True)
class ClientSpec:
    key: str
    name: str
    config: Path | None  # None: the official docs give no file path, so the client is skipped
    marker: Path  # exists only when the client is installed
    stdio_type: bool  # whether the entry carries "type": "stdio"
    trust_ok: bool = False  # Kiro only: autoApprove ["*"] is added with --trust


def client_specs(home: Path, env: Mapping[str, str]) -> list[ClientSpec]:
    copilot_home = Path(env["COPILOT_HOME"]) if env.get("COPILOT_HOME") else home / ".copilot"
    return [
        # https://kiro.dev/docs/mcp/configuration/ (user level: ~/.kiro/settings/mcp.json)
        ClientSpec("kiro", "Kiro", home / ".kiro" / "settings" / "mcp.json", home / ".kiro",
                   stdio_type=False, trust_ok=True),
        # https://cursor.com/docs/context/mcp (global: ~/.cursor/mcp.json)
        ClientSpec("cursor", "Cursor", home / ".cursor" / "mcp.json", home / ".cursor",
                   stdio_type=True),
        # https://code.claude.com/docs/en/mcp (user scope: ~/.claude.json)
        ClientSpec("claude", "Claude Code", home / ".claude.json", home / ".claude.json",
                   stdio_type=True),
        # https://code.visualstudio.com/docs/copilot/reference/mcp-configuration
        # Native Copilot user file: $COPILOT_HOME/mcp-config.json or ~/.copilot/mcp-config.json.
        # GitHub Copilot CLI reads the same file.
        ClientSpec("vscode", "VS Code (Copilot)", copilot_home / "mcp-config.json", copilot_home,
                   stdio_type=True),
        # https://codelabs.developers.google.com/google-workspace-mcp-antigravity
        # Antigravity App, IDE and CLI share ~/.gemini/config/mcp_config.json.
        # The Antigravity docs page (https://antigravity.google/docs/mcp) names no path.
        ClientSpec("antigravity", "Antigravity", home / ".gemini" / "config" / "mcp_config.json",
                   home / ".gemini", stdio_type=True),
    ]


CLIENT_KEYS = ("kiro", "cursor", "claude", "vscode", "antigravity")


def _desired_entry(spec: ClientSpec, trust: bool, server: tuple[str, list[str]] | None = None) -> dict:
    command, args = server if server is not None else (SERVER_COMMAND, SERVER_ARGS)
    entry: dict = {}
    if spec.stdio_type:
        entry["type"] = "stdio"
    entry["command"] = command
    entry["args"] = list(args)
    if trust and spec.trust_ok:
        entry["autoApprove"] = ["*"]
    return entry


def _merged_entry(current: dict | None, desired: dict) -> dict:
    merged = {k: v for k, v in (current or {}).items() if k not in REMOTE_ONLY_KEYS}
    merged.update(desired)
    return merged


def _load(path: Path) -> tuple[dict, bool]:
    """Return (document, existed). A missing or blank file is an empty document."""
    if not path.exists():
        return {}, False
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        return {}, True
    data = json.loads(text)  # json.JSONDecodeError is a ValueError
    if not isinstance(data, dict):
        raise ValueError("the top level is not a JSON object")
    return data, True


def _write(path: Path, data: dict, existed: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if existed and not backup.exists():
        shutil.copy2(path, backup)
    tmp = path.with_name(path.name + ".argus-tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _run_one(spec: ClientSpec, *, remove: bool, trust: bool, dry_run: bool,
             server: tuple[str, list[str]] | None = None, update: bool = False) -> tuple[list[str], bool]:
    """Return (output lines, failed) for one client."""
    if spec.config is None:
        return [f"{spec.key}: skipped, the official docs give no config file path"], False
    if not spec.marker.exists():
        return [f"{spec.key}: skipped, {spec.name} is not installed ({spec.marker} not found)"], False

    try:
        data, existed = _load(spec.config)
    except (OSError, ValueError) as exc:
        return [f"{spec.key}: ERROR {spec.config}: {exc}. Nothing was written."], True

    servers = data.get(ROOT_KEY, {})
    if not isinstance(servers, dict):
        msg = f"{ROOT_KEY} in {spec.config} is not a JSON object. Nothing was written."
        return [f"{spec.key}: ERROR {msg}"], True
    current = servers.get(SERVER_NAME)
    shown: dict | None = None

    if remove:
        if current is None:
            return [f"{spec.key}: skipped, no {SERVER_NAME} entry in {spec.config}"], False
        action = "removed"
        del servers[SERVER_NAME]
    else:
        desired = _desired_entry(spec, trust, server)
        merged = _merged_entry(current, desired)
        if current is None:
            action = "added"
        elif merged == current:
            return [f"{spec.key}: up to date, {spec.config}"], False
        elif not update:
            # A working entry the user made stays; replacing it is an explicit choice.
            return [f"{spec.key}: kept the existing {SERVER_NAME} entry in {spec.config} "
                    "(run with --update to replace it)"], False
        else:
            action = "updated"
        servers[SERVER_NAME] = merged
        shown = desired  # only the fields the installer sets; existing env values are never printed
    data[ROOT_KEY] = servers

    if dry_run:
        verb = {"added": "add", "updated": "update", "removed": "remove"}[action]
        lines = [f"{spec.key}: would {verb} the {SERVER_NAME} entry in {spec.config} (dry run, nothing written)"]
        if shown is not None:
            lines.append(f"    {SERVER_NAME}: {json.dumps(shown, ensure_ascii=False)}")
        return lines, False

    _write(spec.config, data, existed)
    return [f"{spec.key}: {action} {spec.config}"], False


def main(argv: list[str] | None = None, *, home: Path | None = None,
         env: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="argus-install",
        description="Add the ARGUS MCP server to each installed AI IDE. Asks nothing.",
    )
    parser.add_argument("--client", action="append", choices=CLIENT_KEYS, metavar="NAME",
                        help="only this client (repeatable): " + ", ".join(CLIENT_KEYS))
    parser.add_argument("--dry-run", action="store_true",
                        help="print the change and write nothing")
    parser.add_argument("--remove", action="store_true",
                        help="remove the argus entry instead of adding it")
    parser.add_argument("--update", action="store_true",
                        help="replace an existing argus entry (without it an existing entry is kept)")
    parser.add_argument("--trust", action="store_true",
                        help='Kiro only: add "autoApprove": ["*"] to the argus entry')
    args = parser.parse_args(argv)

    home = Path.home() if home is None else Path(home)
    env = os.environ if env is None else env
    specs = client_specs(home, env)
    if args.client:
        specs = [spec for spec in specs if spec.key in args.client]

    server = local_server()
    failed = False
    for spec in specs:
        lines, error = _run_one(spec, remove=args.remove, trust=args.trust, dry_run=args.dry_run,
                                server=server, update=args.update)
        for line in lines:
            print(line, file=sys.stderr if error else sys.stdout)
        failed = failed or error
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
