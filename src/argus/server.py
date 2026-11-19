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

from . import __version__, jobs
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
def studio_guide(custom_scenes: bool = False) -> list[str | Image] | dict:
    """Read this at the start of every session: how to work, what is available, what the user prefers.

    Returns `guide` (the working method: you are the director and the editor, ARGUS
    tools are your eyes, ears and hands), `capabilities` (the registered tools and
    which providers work right now: ElevenLabs, Gemini, edge-tts, faster-whisper,
    Veo API, Google Flow session) and `preferences` (the user's saved lasting
    preferences and corrections, newest last; they override your defaults).
    `preferences_truncated` is true when older entries were left out to keep the
    text short. Call it again with `custom_scenes=true` when you plan custom scenes:
    the result then also has `motion_kit`, the catalogue of ready-made blocks (counters,
    plates, pop-ups, polls, text, effects, scene tracks with cues) that custom components
    import from `'../kit'`.
    `library` is the user's style library: scenes, characters, plates and caption styles
    saved from earlier videos. It has `entries` (the count), `index` (one line per entry)
    and `posters` (the newest entries, at most 8). When it has posters, the result is the
    JSON text followed by those posters as images, in the order of `library.posters`
    (512 px): compare them with the reference you are about to make before you write new
    code. An entry's files are imported by a custom component as
    `import X from './library/<entry>/<File>'`.
    """
    return studio.result_for_model(studio.studio_guide(_registered_tool_names(), custom_scenes=custom_scenes))


@mcp.tool()
def job_status(job_id: str, wait_s: float = 0) -> list[str | Image] | dict:
    """Check a long-running operation that returned a `job_id` instead of a result.

    Tools that can take longer than about 20 seconds (watching a long video,
    rendering, transcribing) keep working in a background process and return
    `{"job_id", "state": "running", ...}` when they are not done in time. Call this
    with that `job_id` and `wait_s=20` to wait on the server until the job ends (at
    most 20 seconds per call; the wait stops early when the job is done or failed).
    Returns `state` (queued|running|done|error), `progress` (0..1, or null when
    unknown), `eta_s` (a rough estimate, only while running with known progress),
    `note`, `elapsed_s`, and then `result` (when done; frames come back as images,
    each listed with its path) or `error` (the error tail, also when the worker
    process died). Starting the same operation again while it runs returns the same job.
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

    provider "api" = official Gemini API (stable, paid - Veo has no free API tier);
    provider "flow" = your logged-in Google Flow browser session (free monthly
    credits, run flow_login once first). Default: ARGUS_VEO_PROVIDER or "api".
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
    """Speak `text` and save a mastered voiceover plus word timings for captions.

    You direct the performance. Choose the voice yourself (see `voice_options`),
    tell the user which voice you picked and why, and write the text for the ear in
    the user's language: short sentences, numbers and abbreviations spelled the way
    they are said. The text is sent unchanged, so write the delivery into it. On
    ElevenLabs `eleven_v3` / `eleven_v4` (v3 is the default) use audio tags such as
    `[whispers]`, `[excited]`, `[sighs]`, `[laughs]` before the words they colour,
    plus punctuation for rhythm: `...` for a hesitation or a pause, a dash for a
    break, CAPITALS for stress. SSML `<break time="1.0s" />` works only on the
    older v2 family (`eleven_multilingual_v2`, flash); v3/v4 do not understand it.
    edge voices (free) cannot act out tags: they are removed before speaking.
    Gemini voices follow bracketed tags too.

    `project` is the work's short name (use the same one for the whole video); the
    files go to `<project>/audio/<name>.mp3` and `<name>.words.json`. `provider`:
    "elevenlabs" (default when a key is configured), "edge" (default without keys,
    free) or "gemini" (only when you ask for it). `voice`: a name or id from
    `voice_options` (ElevenLabs preset names Brian, Adam, George, Daniel also
    work). `model`: an ElevenLabs model id (default from the config). `settings`:
    ElevenLabs `stability`, `similarity_boost`, `style`, `speed` (0.7..1.2),
    `use_speaker_boost`, `language_code`, `seed`; edge `rate` ("+10%"), `pitch`
    ("+2Hz"), `volume`; `language` ("ru") helps word alignment.

    Returns `audio`, `words_path` (a JSON list of `{w, s, e}` in seconds, tags
    removed; use it for captions and for cutting on the voice), `duration`,
    `provider`, `voice`, `model` and `words_source`: "provider" (ElevenLabs or edge
    timings), "faster-whisper" (aligned from the audio) or "none" (no timings:
    `captions_note` says what to install). Long text is split on paragraphs and
    joined, with timings offset correctly. Texts that take longer than ~20 s run in
    the background: you get `{"job_id", "state": "running"}`; call `job_status`.
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
    """Find voices for a narrator or character, and see which voice providers work now.

    Call it before the first voiceover of a project. Its `provider_choice` says which
    providers work (ElevenLabs, edge, Gemini, and a local Voice Studio once it is
    installed), which one is `recommended` (ElevenLabs whenever its key is set) and
    whether to ask: when `ask_user` is true, ask the user which provider they want
    (one line per option, in their language), keep the answer for the whole project
    and do not switch mid-project; with a single working provider just use it. Within
    the chosen provider you pick the voice, not the user: filter by `language` ("ru",
    "en", "Russian"), `gender` ("male" / "female") and a free-text `query` (words such
    as "deep narrator calm"; a voice matches when ANY word occurs, in any case, in its
    name, description, accent, age, gender, use case or language), then choose what
    fits the genre and tell the user your choice.
    Every voice is short: `id`, `name`, `gender`, `age`, `accent`, `language` and a
    `description` of at most 80 characters. Returns `own_voices` (the ElevenLabs
    account's voices, matching language first), `library_voices` (ElevenLabs Voice
    Library voices that the API accepts on the current plan), `library_voices_paid_plan_only`
    (voices that need a paid plan: library voices marked `free_users_allowed=false`, and on the
    free plan every library voice and every own voice that is not premade; do not pick them
    without asking), `plan` (the ElevenLabs tier, or a note when it cannot be read),
    `edge_voices` (free defaults per language), `gemini_voices` (names),
    `providers` (what works right now and why not) and `default_provider`. `limit`
    caps every list (max 50), and the whole answer stays under 6000 characters: when
    it would be longer, the longest lists lose their last voices and `notes` says so,
    so narrow the search with `language`, `gender` and `query` instead of raising `limit`.
    Pass a returned `id` as `voice` to `synthesize_voiceover`.
    With `details=True` (use it once per project, before you write the narration)
    the answer also holds `delivery`, the audio tags and the pacing rules for the
    configured ElevenLabs model (plan the emotion of every line yourself: what it
    feels like, where it breathes, where it stresses, and write it into the text),
    and `elevenlabs_models` (ids, character limits and how each wants pauses and
    emotion written: audio tags for v3/v4, SSML breaks for v2). Without `details`
    neither is returned.
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
    file. It returns contact sheets as images (up to 6 frames each, every tile
    labelled `mm:ss.s  #shot`) and a JSON summary: `shots` (every cut found over the
    whole file as [start, end] seconds), `frames` (time, file path and shot number of
    each frame, full resolution), `sound_events` (times of sharp sounds with strength
    0..1), `transcript_head` (the start of the spoken text), `segments_path` (a JSON
    list of sentences `{s, e, text}`) and `words_path` (a JSON list of `{w, s, e}` per
    word in seconds of the file: read it, or give it to a plan as
    `captions.words.source`). The words and sentences are never listed in the result,
    so read the files when you need them. Whisper is asked to keep fillers, stumbles and repeats
    for English and Russian; for other languages it may tidy them away. The transcript
    needs faster-whisper; without it the summary says so in `transcript_note`.
    `project` is a short name for the work (it decides where the cache and files
    live; use the same name for the whole video). `max_frames` is the frame budget
    (default 24, up to 120): shot starts first, an extra frame in long shots, evenly
    spread when there are more shots than frames. Each call returns 2 contact sheets;
    `pages_total` tells how many pages exist, pass `page=2`, `3`... for the rest.
    `language` is a code like "en" or "ru" (default: detected). The same file is not
    analysed twice: a repeated call returns the cached result (`cache_hit`). Long
    files run in the background: you get `{"job_id", "state": "running"}` and then
    call `job_status(job_id)` until it is done. To read an exact moment closely
    (text, HUD values, colours, the frames around a cut) use `get_frames`.
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
) -> list[str | Image] | dict:
    """Render a plan with the ARGUS engine. Work in this order: stills first, then preview, then final.

    `plan` is the plan object (or the path of a plan .json file); `project` is the
    work's short name (the same for the whole video). Relative file paths in the plan
    (fonts, images, audio, words files) are looked up in the project folder first.
    The plan has `format` ("9:16" or "16:9"), optional `fps` and `duration`, `style`
    ("dark", "light" or tokens with colors, fonts, text_scale, safe_area, background,
    grain), `scenes`, `hud`, `captions`, `audio` (voice, music with `duck`, sfx events).
    Caption words can be drawn in capitals: `captions.style.case` is `"upper"` or `"as_is"` (the default).
    `format` here overrides the plan's. The engine adds no sound effects of its own.

    mode "stills" (default): renders only the frames at `times` (seconds, up to 8; default
    6 spread over the video) and returns them as images with a `path` each. Use this
    again and again while you settle the look; it takes seconds. With `compare`
    = {"video": reference path, "times": [reference seconds]} (same length as
    `times`) every image is side by side: reference on the left, your render on the
    right, both labelled with their time.
    mode "preview": the whole video at half resolution, fast to check motion and timing.
    mode "final": full resolution, then loudness normalised (-14 LUFS), faststart and a
    metadata tag; also saves the plan as `<project>/plan.json`. Run `qa_verify_video`
    on the result.
    Previews and finals take longer than a tool call may wait: you get
    `{"job_id", "state": "running"}`; call `job_status` until it is done. Files go to
    `<project>/renders/<name>-<mode>-<format>.mp4` (stills: `.jpg`); `name` defaults to
    "video".

    Custom scenes: when no built-in scene fits, write a React component into
    `<project>/components/<Name>.tsx` (default export; may import only `react`, `remotion`,
    `../style`, `../kit` (the motion kit: ready-made blocks, see `studio_guide(custom_scenes=true)`)
    other files of that folder and style library files as `./library/<entry>/<File>`, see
    `studio_guide`; no network) and use it as
    `{"kind": "custom", "at": 2, "component": "<Name>", "props": {...}}`. It is
    typechecked on every render. Compiler errors come back as `{"valid": false, "errors":
    ["components/<Name>.tsx(4,9): error TS...", ...]}` and nothing is rendered.
    `plan.cues` names moments for custom scenes: `{"burn": {"word": "сгорает"}, "end": 41.2}`.
    A word cue is where that word is spoken in `captions.words` (optional `nth`, `offset`
    seconds, `prefix*`), so a new voice moves it; a number is seconds. A component reads a
    cue with the kit's `useCue('burn')`, so no times are typed into its props.

    An invalid plan, a missing file or bad `times` returns `{"valid": false, "errors":
    ["scenes[3].kind: ...", ...]}` with every problem as `path: message`, and nothing is
    rendered. `warnings` in the result list what the plan asked for that the engine does
    not draw or apply yet, and risky code in custom components.
    """
    return render.render_video(
        plan, project, mode=mode, times=times, compare=compare, format=format, name=name,
    )


@mcp.tool()
def qa_verify_video(
    video_path: str,
    format: str | None = None,
    frames: int = 4,
    target: str | None = None,
) -> list[str | Image] | dict:
    """Check a finished video for technical defects. Run it on every final render before you publish.

    It measures and never judges the creative work. `format` ("9:16" or "16:9") sets the
    frame size to expect; without it the frame's own shape decides. Hard failures (`passed`
    is false): frame size, frame rate, progressive scan, audio present, integrated loudness
    -14 LUFS +/-1.5, true peak at most -1.0 dBTP, video and audio lengths within 0.5 s of each
    other, and black of 1.0 s or more in the middle of the video. Warnings (`passed` stays
    true): shorter black and black at the edges, a frozen picture of 3 s or more, silence of
    2 s or more in the middle, and, when `target` ("tiktok", "shorts" or "youtube") is given,
    a duration above that platform's limit.
    Every entry in `hard_failures` and `warnings` has `check`, `message` and, where it
    applies, `start` and `end` in seconds. `images` holds `frames` evenly spread frames
    (default 4) and one frame for each black gap and frozen picture, at most 8 in all: look
    at them. Fix every hard failure; judge the warnings yourself. Long videos run in the
    background: you get `{"job_id", "state": "running"}`; call `job_status` until it is done.
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

    Call it after `qa_verify_video` passes on the final renders. `videos` maps "9:16" and/or
    "16:9" to the mp4 path (the files `render_video` makes in mode "final"). Write `texts`
    yourself, for each platform's viewers:
    - "tiktok": {"caption": str, "hashtags": [str]}
    - "shorts": {"title": str, "description": str, "hashtags": [str]} (uses the 9:16 video)
    - "youtube": {"title": str, "description": str, "tags": [str]} (uses the 16:9 video)
    Give only the platforms you publish to. A hashtag gets a "#" when it lacks one.
    `cover_times` ({"9:16": seconds, "16:9": seconds}) picks the cover frame; by default it is
    the first of the QA's evenly spread frames that is not black. `name` sets the file names
    (default: the project name).

    Files go to `<project>/final/`: `<name>_9x16.mp4` and/or `<name>_16x9.mp4` (copied, not
    re-encoded), `<name>_cover_9x16.jpg` (1080x1920) and `<name>_cover_16x9.jpg` (1280x720,
    under 2 MB), and `post.md`. The covers come back as images.
    The export refuses when QA finds a hard failure: nothing is written and `hard_failures`
    says why. A text over a platform's length limit is listed in `violations` and marked in
    post.md; the files are still written, so shorten the text and export again. On success
    the project's `.work/` folder is removed.

    `save_to_library` keeps what worked for the next video: after a good final, offer the
    user to save the custom scenes, characters, plates or caption styles to their style
    library, and pass this only after they agree. It is
    `{"name": "yacht-scenes", "components": ["Art", "Scenes1"], "what": "...", "fits_when": "...",
    "props": "...", "replace": false, "poster_time": 12.5}`. `components` are file names in
    `<project>/components/` (the files they import come along). `what` says what the entry is,
    `fits_when` when to use it (a reference where it fits, and where it does not); at most 200
    and 250 characters, they form the entry's line in the index; `props` (optional, 600) lists
    the props worth changing. `poster_time`
    (optional, seconds) picks the poster frame from the final, else the cover frame is used.
    `replace` must be true to overwrite an entry of the same name. The entry goes to
    `<OMNIFRAME_OUTPUT_DIR>/library/<name>/` with `card.md` and a 512 px `poster.jpg`, and the
    result has a `library` block; `studio_guide` lists the entries from then on.
    A long video runs in the background: you get `{"job_id", "state": "running"}`; call
    `job_status` until it is done.
    """
    return export.export_package(
        project, videos, texts, cover_times=cover_times, name=name, save_to_library=save_to_library
    )


@mcp.tool()
def calculate_beat_grid(audio_path: str, snap_times: list[float] | None = None) -> dict:
    """Measure tempo + beat grid of a music track; snap scene cuts to beats.

    Music-first rhythm: run this on the BGM BEFORE laying out scene timing,
    then put every scene cut on a beat (perceptual threshold ~3 frames).
    snap_times: candidate cut seconds -> returned snapped to the nearest beat
    (with per-cut shift). Offline: numpy + ffmpeg, no network.
    """
    return beats.calculate_beat_grid(audio_path, snap_times)


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

    Call it without `name` to see the scripts in the repo's `scripts/` folder and in
    `ARGUS_SCRIPTS_DIR`: each has a `summary` and an `args` example to copy. Call it with
    `name` (lowercase letters, digits, underscore) and `args` (a JSON object) to run one.
    The script's JSON result comes back as `result`. Set `args["project"]` to run inside
    that project's folder, so relative paths in `args` resolve there; without it the
    script runs in the output folder. A result may list `images` (file paths): they come
    back as pictures. `timeout_s` (default 120, from 1 to 3600) stops a script that runs
    too long; the result then has `timed_out: true`. A script that runs longer than about
    20 seconds continues in the background: call `job_status` with the `job_id`.
    Scripts run with the user's own rights, so run only scripts the user wrote or trusts.
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
    mcp.run()


if __name__ == "__main__":
    main()
