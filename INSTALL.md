# Install ARGUS: from zero to the first video

About 30 minutes, most of it downloads. If a step fails, copy the exact error text. Do not use
`--force` or delete folders to fix it.

Supported: Windows, macOS and Linux. The commands below show Windows PowerShell first, then
macOS and Linux.

## Option B: no clone (uvx or Kiro Power)

Install `uv` (https://docs.astral.sh/uv/), ffmpeg and Node.js 18 or newer. Then use this command as the
MCP server command in your client:

```bash
uvx --from git+https://github.com/vertovhq/argus argus-studio
```

For Kiro, the folder [`kiro-power/`](kiro-power/README.md) is a power that installs the same server with
its guide. Import it from a clone with Add Custom Power.

The first start copies the graphics engine into `~/.argus/engine` and installs its packages in the
background. Check it with the `doctor` tool, or run
`uvx --from git+https://github.com/vertovhq/argus argus-doctor`. Keys go in `~/.argus/.env`. The steps
below (sections 2 to 4) apply only to Option A, the clone.

## 1. Requirements

| Tool | Why | Check |
|---|---|---|
| Python 3.11 or newer | ARGUS server | `python --version` |
| ffmpeg on PATH | probing, cutting, loudness, frames | `ffmpeg -version` |
| Node.js 18 or newer | Remotion render engine (kinetic graphics) | `node --version` |
| Internet | voices (edge-tts), Veo (Flow), Freesound | — |

ffmpeg on Windows: download a build from https://www.gyan.dev/ffmpeg/builds/ (the "essentials"
zip), unpack it to `C:\ffmpeg`, and add `C:\ffmpeg\bin` to PATH. Open a new terminal afterwards so
PATH applies.

## 2. Get the code and create a virtual environment

```powershell
git clone https://github.com/vertovhq/argus.git
cd argus
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
```

## 3. Install

With the venv activated, from the repository folder:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1     # macOS/Linux: bash install.sh
```

The script does four things:

1. `pip install -e ".[dev,pretty,voice]"`: the ARGUS package, tests, `rich` output and the free
   edge-tts voice.
2. Tries to install Chromium through Playwright for the optional Flow route. A failure here is safe to
   ignore; Flow is optional.
3. `npm install` in `engine/`: the Remotion engine.
4. Copies `.env.example` to `.env` if there is no `.env` yet.

If you prefer manual steps, run the same commands yourself:

```powershell
pip install -e ".[dev,pretty,voice]"
cd engine; npm install --no-audit --no-fund; cd ..
copy .env.example .env
```

Optional extras: `pip install -e ".[asr]"` adds faster-whisper for transcripts in `watch_video`
(the model downloads on first use). `pip install -e ".[flow]"` adds Playwright for the Flow route.

## 4. Keys (optional)

Everything in the quickstart works without keys. Add keys when you want better voices or Veo.
Edit `.env` in the repository folder. Never paste keys into a chat.

| Variable | Get it at | Used for |
|---|---|---|
| `ARGUS_GEMINI_API_KEY` | https://aistudio.google.com/apikey | Gemini voices, the model list |
| `ELEVENLABS_API_KEY` | https://elevenlabs.io (API Keys) | ElevenLabs voices |

ElevenLabs keys start with `sk_`. The key is shown once, when you create it. A long hex string
without `sk_` is a key ID, and the API rejects it with `api_key_id_used_as_api_key`.

Veo: the Gemini API shut Veo 3.1 Preview down on 2026-10-22, so `provider="api"` is refused. For Veo
clips, use the Flow route: set `ARGUS_VEO_PROVIDER=flow` in `.env`, then run `flow_login` once from the
chat and sign in with your own Google account. The Flow route is experimental.

Other settings are documented in `.env.example`. `OMNIFRAME_OUTPUT_DIR` sets where projects are written.

## 5. Connect your MCP client

Kiro: create or edit `.kiro/settings/mcp.json` in the workspace (or `~/.kiro/settings/mcp.json` for
every workspace):

```json
{
  "mcpServers": {
    "argus": {
      "command": ".venv/Scripts/python.exe",
      "args": ["-m", "argus"],
      "env": { "OMNIFRAME_OUTPUT_DIR": "./output" }
    }
  }
}
```

macOS and Linux: change the command to `.venv/bin/python`. In the user-level file, use the absolute
path to the venv's Python. The relative path resolves from the workspace root.

Save the file, then open the MCP Server view in Kiro and reload `argus`. Without a reload, the new
tools do not appear.

Other MCP clients: point the command at the venv Python with arguments `-m argus`, or at the
`argus-studio` command when the venv is on PATH.

More examples: [`examples/mcp-config.example.json`](examples/mcp-config.example.json).

## 6. Check the installation

In a terminal, with the venv activated:

```powershell
argus-doctor
```

It prints a table. ✓ means the item works, ✗ means it is missing (the line says what to install), and
⚠ means an optional part is not installed. The check is ready when the required items (Python,
ffmpeg, Node, the engine) show ✓.

In the Kiro chat, ask for `doctor`. It returns the same report as JSON.

## 7. The first video

In the Kiro chat:

1. `Call studio_guide and follow its working order.`
2. `Watch examples/media/moving-shapes-8s.mp4 with watch_video, then get_frames at 2 and 6 seconds. Describe what you see.`
3. `Read examples/media/sample-voiceover.txt and voice it with synthesize_voiceover, project demo.`
4. `Render stills of examples/plans/graphics_9x16.json in project demo at 1, 4 and 8 seconds. Show me the frames.`
5. When the stills look right: `Render a preview, then the final of the same plan.`
6. `Run qa_verify_video on the final file.` Then `export_package` for the upload folder.

For production-quality voice, add your ElevenLabs API key to .env (ELEVENLABS_API_KEY). Without a key ARGUS falls back to a free voice so the example still runs.

Files go to `<OMNIFRAME_OUTPUT_DIR>/projects/demo/`. Long jobs return a `job_id`; ask for `job_status` to check them.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `api_key_id_used_as_api_key` | You pasted a key ID. The ElevenLabs key starts with `sk_`. |
| `argus-doctor` reports ffmpeg or Node missing | PATH did not update. Open a new terminal. |
| `provider api` error mentioning 2026-10-22 | Veo API is shut down. Use `provider="flow"`. |
| New tools are not in the chat | The MCP server was not reloaded after the config change. |
| Render says the engine is installing or not installed (uvx or Kiro Power) | The background install is still running or failed. The `doctor` tool shows the step, and `~/.argus/engine-setup.log` has the output. |
| Tool call timed out | Not an error in most cases. Long work runs in the background; check `job_status`. |
| Render does not match what you wanted | Check the stills first and say what is wrong before the final render. |
