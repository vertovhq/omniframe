"""ARGUS MCP server.

Exposes the video production pipeline as MCP tools: watching footage, voiceover,
Veo clips, rendering, QA, export and the user's own scripts.
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

from . import __version__, engine_setup, jobs
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


def _registered_tool_names() -> list[str]:
    """Names of every tool registered on this server (same attribute in mcp 1.x and 2.x)."""
    return [tool.name for tool in mcp._tool_manager.list_tools()]


@mcp.tool()
def studio_guide(custom_scenes: bool = False, kit_group: str | None = None, full: bool = False) -> list[str | Image] | dict:
    """Read this at the start of every session: the working method, the tools and providers, the user's preferences.

    Returns `guide` (how to work: you direct, ARGUS tools are your eyes, ears and hands),
    `capabilities` (tools and providers that work now) and `preferences` (the user's saved
    corrections; they override your defaults). With `custom_scenes=true` it also returns
    `motion_kit`, the index of kit groups; open one group with `kit_group="hud"` (or `core`,
    `backgrounds`, `transitions`, `energy`, `type`, `bursts`, `depth`, `camera`, `info`) to get its
    blocks and a strip image. `library` lists saved scenes and posters (512 px) to compare with a reference.
    A repeated read with the same content returns one line: `full=true` gives the text again.
    """
    if kit_group:
        return studio.kit_group_for_model(kit_group, full=full)
    guide = studio.studio_guide(_registered_tool_names(), custom_scenes=custom_scenes)
    return studio.result_for_model(studio.once("guide" + (":kit" if custom_scenes else ""), guide, full))


@mcp.tool()
def job_status(job_id: str, wait_s: float = 0) -> list[str | Image] | dict:
    """Check a long-running operation that returned a `job_id`.

    Call it with that `job_id`. `wait_s` (up to 20) waits on the server until the job ends, so
    polling costs fewer calls. Returns `summary` (one sentence: what is happening, what is left),
    `state` (queued, running, done or error), `progress` (0..1 or null), `eta_s` (rough, while
    running), `note`, and then `result` when done (pictures come back as images) or `error` when
    it failed, with the fix in the text. Starting the same operation again while it runs returns the same job.
    """
    return jobs.job_status(job_id, wait_s)


@mcp.tool()
def generate_veo_clip(
    prompt: str,
    output_path: str,
    aspect_ratio: str = "9:16",
    model: str | None = None,
    negative_prompt: str | None = None,
    max_wait_s: float = 600.0,
    provider: str | None = None,
) -> dict:
    """Generate an authentic Veo video clip (default 1080x1920).

    provider "flow" = your logged-in Google Flow browser session (free monthly
    credits, run flow_login once first). Default: ARGUS_VEO_PROVIDER or "api".
    provider "api" is refused for now: Veo 3.1 Preview was shut down in the Gemini
    API on 2026-10-22, and the error says so. Use "flow" until the Omni route ships.
    Renders take 1-3 minutes. Prompts are sent as-is - no content-policy
    workarounds are applied.
    """
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


@mcp.tool()
def flow_login() -> dict:
    """One-time Google Flow login wizard for the "flow" Veo provider.

    Opens a visible browser window: log into your Google account manually and
    wait for Flow to load - the session profile is then saved to disk
    (~/.argus/flow_profile). Afterwards generate_veo_clip(provider="flow") uses
    your free monthly Flow credits without any cookie files. One own account
    only - multi-account credit farming gets accounts banned.
    """
    from .tools.flow_browser import flow_login as impl

    return impl()


@mcp.tool()
def synthesize_voiceover(
    text: str,
    project: str,
    provider: str | None = None,
    voice: str | None = None,
    model: str | None = None,
    name: str = "voice",
    settings: dict | None = None,
) -> dict:
    """Speak `text` and save a mastered voiceover with word timings for captions.

    You direct the performance: choose the voice (see `voice_options`), tell the user which voice
    and why, and write the text for the ear in the user's language. The text is sent unchanged, so
    put the delivery into it: on ElevenLabs v3/v4 use audio tags such as `[whispers]` or `[excited]`
    before the words they colour, plus `...` for a pause, a dash for a break and CAPITALS for stress.
    SSML breaks work only on the older v2 models. edge voices cannot act tags out: they are removed.

    `project` is the video's short name (the same for the whole video); files go to
    `<project>/audio/<name>.mp3` and `<name>.words.json`. `provider`: "elevenlabs" (default with a
    key), "edge" (default without a key) or "gemini" (only when asked). `voice`: a name or id from
    `voice_options`. `model`: an id from `voice_options` `models`. `settings` holds provider
    options (`stability`, `speed`, `language_code`; edge `rate`, `pitch`); `language` helps alignment.

    Returns `summary`, `audio`, `project_folder`, `words_path` (`{w, s, e}` in seconds, tags removed),
    `duration`, `provider`, `voice`, `model`, `words_source` ("provider", "faster-whisper" or "none";
    `captions_note` says what to install) and `project_note` when the project already holds another
    video's plan or renders. A 429 from ElevenLabs is retried; the summary then says how long to wait.
    Long texts run in the background: call `job_status`.
    """
    from .tools.voiceover import synthesize_voiceover as impl

    return impl(text, project, provider=provider, voice=voice, model=model, name=name, settings=settings)


@mcp.tool()
def voice_options(
    language: str | None = None,
    gender: str | None = None,
    query: str | None = None,
    limit: int = 10,
    details: bool = False,
) -> dict:
    """Find voices for a narrator or character, and see which providers work now.

    Call it before the first voiceover of a project. `provider_choice` says which providers work,
    which one is `recommended` (ElevenLabs when its key is set) and whether to `ask_user`: then ask the
    user once, in their language, and keep the answer for the project. Filter by `language` ("ru", "en"),
    `gender` ("male" or "female") and `query` (words; a voice matches when ANY word occurs in its name,
    description, accent, age or labels). Every voice is short: `id`, `name`, `gender`, `age`, `accent`,
    `language`, `description` (80 characters).

    Lists: `own_voices` (the account's voices), `library_voices`, `library_voices_paid_plan_only` (do not
    pick these without asking; on the free plan every library voice and every non-premade own voice is
    here), `edge_voices`, `gemini_voices`. `plan` is the ElevenLabs tier, `models` the usable models
    (newest first, `default: true` marks the one ARGUS uses), `providers` what works and why not,
    `errors` the cause of any failed list (HTTP code, missing key permission). An empty list comes with a
    `notes` line that says why. Each list is capped at `limit` (max 50); the answer stays under 9000
    characters. `details=True` adds `delivery` (audio tags and pacing rules) and leaves room for fewer voices.
    Pass a returned `id` as `voice` to `synthesize_voiceover`.
    """
    from .tools.voiceover import voice_options as impl

    return impl(language=language, gender=gender, query=query, limit=limit, details=details)


@mcp.tool()
def watch_video(
    path: str,
    project: str,
    max_frames: int = watch.DEFAULT_MAX_FRAMES,
    transcript: bool = True,
    language: str | None = None,
    page: int = 1,
) -> list[str | Image] | dict:
    """Watch a local video (a reference, or the user's footage) and get what a viewer would notice.

    Use it on every reference and on every recording you will edit, one call per
    file. The default is one contact sheet of 12 frames (labelled `mm:ss.s  #shot`), not one
    image per frame. Use the JSON first: `shots` (cuts as [start, end] seconds), `sound_events`,
    `transcript_head`, `segments_path` (sentences `{s, e, text}`) and `words_path` (`{w, s, e}` per
    word, in seconds: read the file or give it to a plan as `captions.words.source`). Words and
    sentences are never listed inline. Then call `get_frames` for the exact moments that matter.
    `max_frames` (default 12, up to 120) sets the budget; `page=2` gives the next sheets when
    `pages_total` says there are more. `project` names the work and its cache. Fillers and repeats
    are kept for English and Russian speech. The transcript needs faster-whisper (`transcript_note`
    says when it is missing). A repeated call on the same file returns the cache (`cache_hit`).
    Long files run in the background: call `job_status(job_id)` until it is done.
    """
    return watch.watch_video(
        path, project, max_frames=max_frames, transcript=transcript, language=language, page=page,
    )


@mcp.tool()
def get_frames(
    path: str,
    times: list[float],
    crop: list[float] | None = None,
    max_side: int = 1024,
) -> list[str | Image] | dict:
    """Look at exact frames of a local video: one image per time in seconds.

    Use it to read what a contact sheet is too small to show: fonts, HUD values,
    colours, layout, or the frames just before and after a cut (for example
    times=[12.40, 12.48, 12.56]). At most 8 times per call; extra times are listed in
    `skipped_times`. `crop` is `[x, y, w, h]` as fractions of the frame (each 0..1,
    x+w <= 1, y+h <= 1): [0, 0, 0.5, 0.25] is the top-left corner (half the width, a quarter of
    the height), shown enlarged. Images are downscaled to `max_side` pixels on the longest
    side (64..2048, default 1024); the summary lists each image's time and path, plus
    `full_path` of the full-resolution file.
    """
    return watch.get_frames(path, times, crop=crop, max_side=max_side)


@mcp.tool()
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
) -> list[str | Image] | dict:
    """Render a plan with the ARGUS engine. Order: stills, then preview, then final.

    mode "stills" (default) renders the frames at `times` (seconds, up to 12; default 6 spread
    over the video) as one contact sheet, or one image for a single frame. It takes seconds: use
    it to settle the look. `compare` = {"video": reference path, "times": [seconds]} (same length
    as `times`) puts each reference frame left of its render. Unchanged frames are not sent again.
    mode "preview" renders the whole video at half size. mode "final" renders full size, then
    normalises loudness (-14 LUFS), and saves `<project>/plan.json`. `then: ["qa"]` on a final runs
    the technical QA in the same job. Fast mode: when the user says "no checks", skip the stills
    and render the preview directly; the user watches it.
    mode "audio" mixes the sounds without a browser and returns the timeline image and `warnings`;
    look at it before the preview. `save_sounds` saves approved sounds to the library.

    `plan` is the plan object or the path of a .json file; `project` is the video's short name.
    Relative file paths in the plan are looked up in the project folder first. The plan keys are in
    `studio_guide`: `format` ("9:16" or "16:9"), `style`, `scenes`, `captions` (`mode` phrase, word
    or headline; `style.case` "upper" or "as_is"), `audio`, `cues`. The engine adds no sound effects.
    Custom scenes are `{"kind": "custom", "component": "<Name>"}` with `<project>/components/<Name>.tsx`
    (see `studio_guide(custom_scenes=true)`). Compile errors return `{"valid": false, "errors": [...]}`.

    An invalid plan, a missing file or bad `times` returns `{"valid": false, "errors":
    ["scenes[3].kind: ...", ...]}`, one `path: message` per problem; nothing renders. Preview and final
    take longer than a tool call: you get `{"job_id", "state": "running"}`, then call `job_status`.
    Results have `summary`, `timing` (seconds per stage) and `warnings`. Files go to
    `<project>/renders/<name>-<mode>-<format>.mp4` (stills: `.jpg`).
    """
    return render.render_video(
        plan, project, mode=mode, times=times, compare=compare, format=format, name=name,
        save_sounds=save_sounds, then=then,
    )


@mcp.tool()
def qa_verify_video(
    video_path: str,
    format: str | None = None,
    frames: int = 4,
    target: str | None = None,
) -> list[str | Image] | dict:
    """Check a finished video for technical defects. Run it on every final render before you publish.

    It measures and never judges the creative work. `format` ("9:16" or "16:9") sets the frame size to
    expect. Hard failures (`passed` false): frame size, frame rate, progressive scan, audio present,
    loudness -14 LUFS +/-1.5, true peak at most -1.0 dBTP, audio and video lengths within 0.5 s, black
    of 1.0 s or more in the middle. Warnings (`passed` stays true): shorter black, a frozen picture of
    3 s or more, silence of 2 s or more, and a duration above the `target` platform limit ("tiktok",
    "shorts", "youtube"). A `-preview-` file reports size and loudness as warnings only.
    Each entry in `hard_failures` and `warnings` has `check`, `message`, and `start` and `end` when they
    apply. `images` holds at most 8 frames, including the black and frozen moments: look at them. Fix
    every hard failure. Long videos run in the background: call `job_status`.
    """
    return qa.qa_verify_video(video_path, format=format, frames=frames, target=target)


@mcp.tool()
def export_package(
    project: str,
    videos: dict[str, str],
    texts: dict,
    cover_times: dict[str, float] | None = None,
    name: str | None = None,
    save_to_library: dict | None = None,
) -> list[str | Image] | dict:
    """Package a finished video for publishing: the final folder with videos, covers and post.md.

    Call it after `qa_verify_video` passes. `videos` maps "9:16" and/or "16:9" to the mp4 paths from
    `render_video` mode "final". Write `texts` yourself, per platform, and give only the platforms you
    publish to: "tiktok": {"caption", "hashtags"}; "shorts": {"title", "description", "hashtags"} (uses
    the 9:16 video); "youtube": {"title", "description", "tags"} (uses the 16:9 video). `cover_times`
    ({"9:16": seconds, "16:9": seconds}) picks the cover frame; `name` sets the file names.

    Files go to `<project>/final/`: the videos (copied), covers as jpg and `post.md`. The covers come back
    as images. The export refuses when QA has a hard failure and writes nothing. A text over a platform's
    length limit is listed in `violations` and marked in post.md; the files are still written, so shorten
    the text and export again. A long export runs in the background: call `job_status`.

    `save_to_library` (only after the user agrees to keep a good scene): `{"name", "components": [file
    names in <project>/components/], "what", "fits_when", "props", "replace", "poster_time"}`. The entry
    goes to the style library, where `studio_guide` lists it from then on.
    """
    return export.export_package(
        project, videos, texts, cover_times=cover_times, name=name, save_to_library=save_to_library
    )


@mcp.tool()
def calculate_beat_grid(
    audio_path: str, snap_times: list[float] | None = None, project: str | None = None,
) -> dict:
    """Measure tempo + beat grid of a music track; snap scene cuts to beats.

    Music-first rhythm: run this on the BGM BEFORE laying out scene timing,
    then put every scene cut on a beat (perceptual threshold ~3 frames).
    snap_times: candidate cut seconds -> returned snapped to the nearest beat
    (with per-cut shift). Pass `project` so the full beat list is written to that
    project's audio folder. The reply gives `bpm`, `confidence`, `beat_count`, the first
    beats and `beats_path` (every beat time, in JSON). Offline: numpy + ffmpeg, no network.
    """
    return beats.calculate_beat_grid(audio_path, snap_times, project=project)


@mcp.tool()
def search_sfx(query: str, license_policy: str = "cc0", min_duration: float = 0.0,
               max_duration: float | None = None, limit: int = 8, pages: int = 1) -> dict:
    """Search Freesound for SFX candidates (CC0, or CC0+CC-BY with license_policy="by").

    Motivated sound effects rule: describe the SOURCE ("paper slide",
    "short cinematic impact"), not an abstract mood. Returns candidates with
    id, title, author, duration, license label, downloads, rating, page URL.
    Audio rule: one sound max once per 3 beats, variations instead of copies.
    No API key. Picks up real varied sounds for the SFX pool per project.
    """
    return sfx.search_freesound(query, license_policy, min_duration, max_duration, limit, pages)


@mcp.tool()
def download_sfx(ids: list[str], out_dir: str, license_policy: str = "cc0") -> dict:
    """Download Freesound SFX (fs:12345 ...) into the project's audio dir.

    Verifies the actual license page again before each download, saves
    audio-manifest.json + FREESOUND-CREDITS.md (CC-BY requires attribution
    in the published video description). Files are HQ MP3 previews.
    """
    return sfx.download_freesound(ids, out_dir, license_policy)


@mcp.tool()
def learn_and_record_memory(
    lesson_title: str,
    user_directive: str,
    technical_rule: str,
) -> dict:
    """Save a lasting user preference or correction; `studio_guide` returns it in every future session.

    Record only what stays true across videos: the user's standing preferences
    ("always...", "never...", their handle, language, voice or brand colours) and
    corrections to your general approach that they want kept. Never record
    per-iteration tweaks to the video in progress ("make the title bigger",
    "cut the second scene"): those belong to this session only.
    lesson_title: short name of the preference. user_directive: what the user said,
    close to their words. technical_rule: how you will apply it from now on.
    """
    return memory.learn_and_record_memory(lesson_title, user_directive, technical_rule)


@mcp.tool()
def run_script(
    name: str | None = None,
    args: dict | None = None,
    timeout_s: float = scripts_runner.DEFAULT_TIMEOUT_S,
) -> list[str | Image] | dict:
    """Run one of the user's own Python scripts, or list them when `name` is left out.

    Without `name` it lists the scripts in the repo's `scripts/` folder and in `ARGUS_SCRIPTS_DIR`, each
    with a `summary` and an `args` example. With `name` (lowercase letters, digits, underscore) and `args`
    (a JSON object) it runs one and returns its JSON as `result`. `args["project"]` runs it inside that
    project's folder. A result may list `images` (paths), which come back as pictures. `timeout_s` (default
    120) stops a long script with `timed_out: true`. Run only scripts the user wrote or trusts.
    """
    return scripts_runner.run_script(name, args, timeout_s=timeout_s)


@mcp.tool()
def doctor(check_flow: bool = False) -> dict:
    """One-command environment self-check (same report as the argus-doctor CLI).

    Critical (a failure makes `ok` false): python >=3.11; ffmpeg/ffprobe on PATH (or
    ARGUS_FFMPEG/ARGUS_FFPROBE); Node >=18 + npx; the engine (engine/node_modules with
    remotion, @remotion/renderer and @remotion/bundler; hint: cd engine && npm install);
    numpy and Pillow; OMNIFRAME_OUTPUT_DIR exists/created.
    Optional (a warning only): faster-whisper (transcripts), edge-tts (free voice, with a
    live 1-word synthesis probe), playwright+chromium (critical when check_flow=True),
    Gemini key and ElevenLabs key presence.
    Returns JSON: {checks, critical_failures, ok}.
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
