# ARGUS — tech steering

## Stack

- Python >= 3.11 MCP server in `src/argus` (mcp SDK `MCPServer`, FastMCP-style decorators).
- ffmpeg / ffprobe for probing, cutting, proxies, frame extraction, loudness, QA.
- Remotion 4.0.540 engine in `engine/` (React 18, TypeScript) — the only video renderer.
- Optional: faster-whisper (transcripts), edge-tts (free voice), playwright (Veo via Flow),
  google-genai (Veo API, Gemini TTS). ElevenLabs is called over REST with `urllib`.

## Commands (Windows, run from repo root)

- Tests: `.venv\Scripts\python.exe -m pytest -q`
- Engine typecheck: `node engine/node_modules/typescript/bin/tsc --noEmit -p engine`
- Environment check: `.venv\Scripts\argus-doctor`
- Renders are started by the tools themselves (node scripts in `engine/scripts/`).

## Terminal on this machine (Kiro IDE, Windows)

- `execute_pwsh` often returns before the command ends and shows only the echoed
  command, with exit code -1. The command still runs. Never trust its printed output.
- Pattern that works: send all output to a file, then read the file with `read_file`.
  `& { <commands> } 2>&1 | Out-File -Encoding utf8 "$env:TEMP\argus_out.txt"`
  If the file is missing on the first read, read it once more (the command may still run).
- Long runs (pytest, renders): write output and the exit code to files, then poll.
  `& { .venv\Scripts\python.exe -m pytest -q 2>&1 | Out-File -Encoding utf8 "$env:TEMP\argus_pytest.txt"; "exit=$LASTEXITCODE" | Out-File -Encoding utf8 "$env:TEMP\argus_pytest_exit.txt" }`
  Read `argus_pytest_exit.txt` until it exists; then read the tail of `argus_pytest.txt`.
  For a run longer than a minute start it detached (`Start-Process powershell.exe -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',<script>`), so the shell stays free.
- Never wait inside the shell (`Start-Sleep` loops): the next commands queue behind the loop and look dead. Poll by reading the exit file again in a later step.
- Never start a second pytest or render while one runs: they share `engine/` and lock files. Before starting one, check for running ones:
  `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match '-m pytest' }`.
  A killed run can leave `engine/.render.lock` and a changed `engine/src/custom/registry.ts`; when no run is alive, delete the lock and `git checkout -- engine/src/custom/registry.ts`.
- Keep temp files in `$env:TEMP`, not in the repo. `*>&1` does not work inside a pipeline; use `2>&1`.

## Code conventions

- Tool logic lives in `src/argus/tools/<name>.py`. `server.py` only declares
  `@mcp.tool()` wrappers whose docstrings are written for the model: what the tool
  does, when to use it, what it returns.
- Tools return a dict that includes `"engine": f"ARGUS {__version__}"`, or, when they
  return pictures, a list `[summary_json_text, Image, Image, ...]` built with
  `argus.media_out.tool_result()`.
- All ffmpeg calls go through `argus.ffmpeg`. On Windows close temp file handles
  before ffmpeg touches them (`temp_sibling`).
- Paths: accept `str`, resolve with `Path(...).resolve()`. Write only inside the
  project directory (`argus.project.project_dir`) or `OMNIFRAME_OUTPUT_DIR`.
- Anything that can take longer than ~20 s goes through `argus.jobs.run_or_detach`.
- Core dependencies: mcp, google-genai, python-dotenv, numpy, Pillow (pydantic comes
  with mcp). Optional extras: `voice` (edge-tts), `asr` (faster-whisper),
  `flow` (playwright), `pretty` (rich), `dev` (pytest). Ask before adding others.
- Secrets come only from env / `.env`. Never print or log keys.
- Tests are offline: synthetic media via ffmpeg `lavfi`, network mocked. Tests that
  need the engine skip when `engine/node_modules` is missing.

## Rules for the implementing agent

- Do exactly the current task from `.kiro/specs/argus-v2/tasks.md`. Do not start the next one.
- Read only the `design.md` sections the task points to; do not re-explore the whole repo.
- Do not read or edit `skills/` unless the task says so.
- Never edit the user's `KNOWLEDGE_BASE.md` content except where a task says so.
- Change tests together with behaviour. Keep the suite green.
- When an external API detail is uncertain (ElevenLabs model ids and endpoints,
  platform text limits, Kiro config fields), check the official docs first and put
  the source URL in a code comment next to the constant.
- Mark a task done only after its **Verify** steps pass. Report what you verified.

## Build log (after every task)

- After a task's Verify steps pass, append one entry to `docs/BUILD_LOG.md` using its entry template (max 8 lines): what was built, bugs hit with symptom → cause → fix, which Kiro feature helped (be concrete; write "none" if none), what was verified and the result.
- Leave "Credits" for the author. Facts only: no marketing words, no invented numbers.
- Detailed reports only when the author asks; save them as `.kiro/specs/argus-v2/taskN.md` (existing convention).
