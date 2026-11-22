"""ARGUS MCP server.

Exposes the video production pipeline as MCP tools: watching footage, voiceover,
Veo clips, rendering, QA, export and the user's own scripts.

Tool descriptions are sent to the model on every turn, so they stay short. Details live in
the guide sections (`studio_guide(section=...)`, see `STUDIO_GUIDE.md` section 10).
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    # mcp >= 2.x
    from mcp.server.mcpserver import MCPServer
except ImportError:  # pragma: no cover
    # mcp 1.x (FastMCP era) — same decorator & run API
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore[no-redef]

from . import __version__, economy, engine_setup, jobs
from .config import CONFIG
from .media_out import Image
from .tools import beats, export, memory, qa, render, scripts_runner, sfx, studio, watch

mcp = MCPServer(
    "Argus",
    instructions=(
        "ARGUS turns you into a video editor and producer for TikTok, Shorts and YouTube. "
        "Call `studio_guide` at the start of every session: it holds the working method and "
        "the user's saved preferences. You make every creative decision. ARGUS tools watch "
        "(`watch_video`, `get_frames`), speak (`synthesize_voiceover`), generate "
        "(`generate_veo_clip`), render (`render_video`), check (`qa_verify_video`) and package "
        "(`export_package`). Operations that take long return a `job_id`; poll `job_status`."
    ),
)


def _strip_titles(node):
    """A JSON schema without its "title" strings. pydantic adds one per parameter; argument checks do not use them.

    A parameter named "title" is kept: its entry in "properties" is a dict, not a string.
    """
    if isinstance(node, dict):
        return {key: _strip_titles(value) for key, value in node.items() if not (key == "title" and isinstance(value, str))}
    if isinstance(node, list):
        return [_strip_titles(value) for value in node]
    return node


def _tool(fn):
    """`@mcp.tool()` that also writes the reply-size log line and drops the schema titles (task 20.10 item 20)."""
    registered = mcp.tool()(economy.measured(fn))
    for tool in mcp._tool_manager.list_tools():
        if tool.name == fn.__name__:
            for attr in ("parameters", "inputSchema"):
                schema = getattr(tool, attr, None)
                if isinstance(schema, dict):
                    setattr(tool, attr, _strip_titles(schema))
    return registered


def _registered_tool_names() -> list[str]:
    """Names of every tool registered on this server (same attribute in mcp 1.x and 2.x)."""
    return [tool.name for tool in mcp._tool_manager.list_tools()]


@_tool
def studio_guide(
    section: str | None = None,
    project: str | None = None,
    custom_scenes: bool = False,
    kit_group: str | None = None,
    full: bool = False,
) -> list[str | Image] | dict:
    """Start every session here: the working method, the saved preferences, the budget rules.

    Without arguments: the core guide and an index of sections. `section="5"` (or a name) returns one
    section. `project` adds a resume of at most 5 lines from that project's state. `kit_group="hud"`
    returns one motion-kit group with its strip image. A repeated read with the same content is one
    line; `full=true` gives the text again.
    """
    if kit_group:
        return studio.kit_group_for_model(kit_group, full=full)
    if section:
        return studio.section_for_model(section, full=full)
    guide = studio.studio_guide(_registered_tool_names(), custom_scenes=custom_scenes, project=project)
    return studio.result_for_model(studio.once("guide" + (":kit" if custom_scenes else ""), guide, full))


@_tool
def job_status(job_id: str, wait_s: float = jobs.DEFAULT_WAIT_S) -> list[str | Image] | dict:
    """Check a job_id from a long tool. It waits on the server (`wait_s`, default and max 20 s) until the job ends.

    Returns `summary`, `state`, `progress`, `note`, and `result` (pictures come as images) or `error`.
    """
    return jobs.job_status(job_id, wait_s)


@_tool
def generate_veo_clip(
    prompt: str = "",
    output_path: str = "",
    aspect_ratio: str = "9:16",
    model: str | None = None,
    negative_prompt: str | None = None,
    max_wait_s: float = 600.0,
    provider: str | None = None,
    login: bool = False,
) -> dict:
    """Make a Veo clip for an AI scene (1080x1920 by default). Takes 1-3 minutes.

    `provider="flow"` uses the logged-in Google Flow session. `login=true` opens the one-time Flow
    login window instead and generates nothing. Prompts are sent unchanged.
    """
    if login:
        from .tools.flow_browser import flow_login as login_impl

        return login_impl()
    from .tools.veo import generate_veo_clip as impl

    return impl(
        prompt,
        output_path,
        aspect_ratio=aspect_ratio,
        model=model,
        negative_prompt=negative_prompt,
        max_wait_s=max_wait_s,
        provider=provider,
    )


@_tool
def synthesize_voiceover(
    text: str,
    project: str,
    provider: str | None = None,
    voice: str | None = None,
    model: str | None = None,
    name: str = "voice",
    settings: dict | None = None,
) -> dict:
    """Speak `text` into `<project>/audio/<name>.mp3` with word timings for captions.

    Pick the voice with `voice_options` first.
    Returns `summary`, `audio`, `words_path`, `duration`, `words_source`, and `project_note` when the
    project holds another video's work. Long texts run in the background: call `job_status`.
    """
    from .tools.voiceover import synthesize_voiceover as impl

    return impl(text, project, provider=provider, voice=voice, model=model, name=name, settings=settings)


@_tool
def voice_options(
    language: str | None = None,
    gender: str | None = None,
    query: str | None = None,
    limit: int = 10,
    details: bool = False,
) -> dict:
    """List voices, models and providers that work with the user's keys. Call before the first voiceover.

    Filters: `language`, `gender`, `query`. Each list is capped at `limit` (max 50). A failed list
    returns its cause in `errors`; `provider_choice.ask_user` says when to ask the user which one.
    """
    from .tools.voiceover import voice_options as impl

    return impl(language=language, gender=gender, query=query, limit=limit, details=details)


@_tool
def watch_video(
    path: str,
    project: str,
    max_frames: int = watch.DEFAULT_MAX_FRAMES,
    transcript: bool = True,
    language: str | None = None,
    page: int = 1,
) -> list[str | Image] | dict:
    """Watch a local video (a reference or the user's footage): one contact sheet, cuts and sound events.

    Call it once per file. Returns `shots`, `sound_events` and `segments_path` / `words_path` files.
    Then call `get_frames` for the exact moments that matter. `page=2` gives the next sheets.
    """
    return watch.watch_video(
        path, project, max_frames=max_frames, transcript=transcript, language=language, page=page,
    )


@_tool
def get_frames(
    path: str,
    times: list[float],
    crop: list[float] | None = None,
    max_side: int = 1024,
) -> list[str | Image] | dict:
    """Look at up to 8 exact frames of a video, one image per time in seconds.

    Use it for small text, fine detail, and the frames around a cut. `crop` is `[x, y, w, h]` as
    fractions of the frame.
    """
    return watch.get_frames(path, times, crop=crop, max_side=max_side)


@_tool
def render_video(
    plan: dict | str,
    project: str,
    mode: str = "stills",
    times: list[float] | None = None,
    compare: dict | None = None,
    format: str | None = None,
    name: str = "video",
    save_sounds: list[dict] | None = None,
    then: list[str] | None = None,
    export: dict | None = None,
) -> list[str | Image] | dict:
    """Render a plan: stills (contact sheet), audio (sound timeline), preview (half size) or final (-14 LUFS).

    An invalid plan returns `errors` with paths and renders nothing. Long renders return a `job_id`.
    `then: ["qa", "export"]` runs QA and the export in the same job (`export` = export_package arguments).
    If the user says "no checks", go straight to the preview.
    """
    return render.render_video(
        plan, project, mode=mode, times=times, compare=compare, format=format, name=name,
        save_sounds=save_sounds, then=then, export=export,
    )


@_tool
def qa_verify_video(
    video_path: str,
    format: str | None = None,
    frames: int = 4,
    target: str | None = None,
) -> list[str | Image] | dict:
    """Check a finished video for technical defects only. Run it on every final render before publishing.

    Returns `passed`, `hard_failures` and `warnings`, each with `check`, `message`, and `start`/`end`,
    and up to 8 frames to look at. It never judges the creative work.
    """
    return qa.qa_verify_video(video_path, format=format, frames=frames, target=target)


@_tool
def export_package(
    project: str,
    videos: dict[str, str],
    texts: dict,
    cover_times: dict[str, float] | None = None,
    name: str | None = None,
    save_to_library: dict | None = None,
) -> list[str | Image] | dict:
    """Write the publishing folder: videos, covers and post.md, under `<project>/final/`.

    `videos` maps "9:16" and/or "16:9" to final mp4 files. `texts` holds the copy per platform (tiktok,
    shorts, youtube). Refused when QA has a hard failure. Returns `economy` (the project's totals).
    """
    return export.export_package(
        project, videos, texts, cover_times=cover_times, name=name, save_to_library=save_to_library
    )


@_tool
def calculate_beat_grid(
    audio_path: str, snap_times: list[float] | None = None, project: str | None = None,
) -> dict:
    """Measure the tempo and beats of a music track, and snap cut times to beats.

    Run it on the music before scene timing. The full beat list goes to a file.
    """
    return beats.calculate_beat_grid(audio_path, snap_times, project=project)


@_tool
def search_sfx(
    query: str = "",
    license_policy: str = "cc0",
    min_duration: float = 0.0,
    max_duration: float | None = None,
    limit: int = 8,
    pages: int = 1,
    download: list[str] | None = None,
    out_dir: str | None = None,
) -> dict:
    """Search Freesound sound effects by the source of the sound, or download some by id.

    Results have `id`, `title`, `license`, `page_url`. `download=["fs:12345"]` with `out_dir` saves the
    files, the manifest and the credits (CC-BY needs credit in the description).
    """
    if download:
        if not out_dir:
            return {"error": "download needs out_dir: the project's audio folder"}
        return sfx.download_freesound(download, out_dir, license_policy)
    return sfx.search_freesound(query, license_policy, min_duration, max_duration, limit, pages)


@_tool
def learn_and_record_memory(
    lesson_title: str,
    user_directive: str,
    technical_rule: str,
) -> dict:
    """Save a lasting user preference or correction; `studio_guide` returns it in every session.

    Record standing preferences only, never a tweak to the video in progress.
    """
    return memory.learn_and_record_memory(lesson_title, user_directive, technical_rule)


@_tool
def run_script(
    name: str | None = None,
    args: dict | None = None,
    timeout_s: float = scripts_runner.DEFAULT_TIMEOUT_S,
) -> list[str | Image] | dict:
    """List the user's own Python scripts (no `name`), or run one with `args` as a JSON object.

    Run only scripts the user wrote or trusts. `args["project"]` runs it inside that project's folder.
    """
    return scripts_runner.run_script(name, args, timeout_s=timeout_s)


@_tool
def doctor(check_flow: bool = False) -> dict:
    """Check the environment: the same report as the argus-doctor command.

    Returns `checks`, `critical_failures` and `ok`. Optional checks only warn.
    """
    from .doctor import run_checks

    return run_checks(flow=True if check_flow else None)


def startup_banner() -> str:
    """One status line for stderr; the tool count is read from the registered tools."""
    banner = (
        f"[ARGUS] Studio v{__version__} ACTIVE | {len(_registered_tool_names())} tools | "
        f"{CONFIG.fps:.0f} fps | output: {Path(CONFIG.output_dir)}"
    )
    if not CONFIG.gemini_api_key and not CONFIG.elevenlabs_api_key:
        banner += " | API keys: MISSING (paid providers disabled, offline tools OK)"
    return banner


def main() -> None:
    """Run the MCP server over stdio."""
    print(startup_banner(), file=sys.stderr)
    try:
        jobs.cleanup_old_jobs()
    except Exception as exc:  # housekeeping must never stop the server
        print(f"[ARGUS] job cleanup skipped: {exc}", file=sys.stderr)
    try:
        engine_setup.ensure_started()  # no-op for a repository checkout; never waits
    except Exception as exc:
        print(f"[ARGUS] engine setup not started: {exc}", file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
