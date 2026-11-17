"""ARGUS MCP server.

Exposes the vertical-video production pipeline as MCP tools:
Veo clips, mastered voiceover, karaoke subtitles, acoustic timeline,
master assembly and QA verification.
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
from .tools import assemble, beats, memory, qa, sfx, studio, subtitles, timeline, watch

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
def studio_guide() -> dict:
    """Read this at the start of every session: how to work, what is available, what the user prefers.

    Returns `guide` (the working method: you are the director and the editor, ARGUS
    tools are your eyes, ears and hands), `capabilities` (the registered tools and
    which providers work right now: ElevenLabs, Gemini, edge-tts, faster-whisper,
    Veo API, Google Flow session) and `preferences` (the user's saved lasting
    preferences and corrections, newest last; they override your defaults).
    `preferences_truncated` is true when older entries were left out to keep the
    text short.
    """
    return studio.studio_guide(_registered_tool_names())


@mcp.tool()
def job_status(job_id: str) -> list[str | Image] | dict:
    """Check a long-running operation that returned a `job_id` instead of a result.

    Tools that can take longer than about 20 seconds (watching a long video,
    rendering, transcribing) keep working in a background process and return
    `{"job_id", "state": "running", ...}` when they are not done in time. Call this
    with that `job_id` every 10-20 seconds until `state` is `done` or `error`.
    Returns `state` (queued|running|done|error), `progress` (0..1, or null when
    unknown), `note`, `elapsed_s`, and then `result` (when done; frames come back as
    images, each listed with its path) or `error` (the error tail, also when the
    worker process died). Starting the same operation again while it runs returns
    the same job.
    """
    return jobs.job_status(job_id)


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
) -> dict:
    """Find voices for a narrator or character, and see which voice providers work now.

    Call it before the first voiceover of a project. Its `provider_choice` says which
    providers work (ElevenLabs, edge, Gemini, and a local Voice Studio once it is
    installed), which one is `recommended` (ElevenLabs whenever its key is set) and
    whether to ask: when `ask_user` is true, ask the user which provider they want
    (one line per option, in their language), keep the answer for the whole project
    and do not switch mid-project; with a single working provider just use it. Within
    the chosen provider you pick the voice, not the user: filter by `language` ("ru",
    "en", "Russian"), `gender` ("male" / "female") and a free-text `query` ("deep
    narrator", "calm", "energetic"), then choose what fits the genre and tell the user
    your choice. With an ElevenLabs key, `delivery` lists the audio tags and the
    pacing rules for the configured model: plan the emotion of every line yourself
    (what it feels like, where it breathes, where it stresses) and write it into the
    text. Returns `own_voices` (the ElevenLabs account's voices, matching language first,
    each with id, name, gender, age, accent, use case, `preview_url`),
    `library_voices` (ElevenLabs Voice Library search; through the API they need a
    paid plan), `edge_voices` (free defaults per language), `gemini_voices`
    (names), `providers` (what works right now and why not), `default_provider`,
    and `elevenlabs_models` (ids, character limits and how each wants pauses and
    emotion written: audio tags for v3/v4, SSML breaks for v2). `limit` caps every
    list (max 50). Pass a returned `id` as `voice` to `synthesize_voiceover`.
    """
    from .tools.voiceover import voice_options as impl

    return impl(language=language, gender=gender, query=query, limit=limit)


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
    0..1), `segments` (spoken text with timecodes) and `words_path` (a words.json file
    with `{w, s, e}` per word, stumbles and repeats kept). The transcript needs
    faster-whisper; without it the summary says so in `transcript_note`.
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
def build_pop_subtitles(
    timestamps_json_path: str,
    output_ass_path: str,
    style: str = "clean",
    highlight_color: str = "#FFE066",
    accent: list[str] | None = None,
    accent_color: str = "#4DA3FF",
) -> dict:
    """Generate frame-accurate karaoke subtitles (.ass).

    Input: JSON list of {word, start, end} (seconds). One word per cue,
    centered at eye level (MarginV 420), bold wide font.
    Styles: "clean" (default - white text, soft shadow, modern), "outline"
    (white with thick black outline, classic shorts), "pop" (legacy yellow).
    accent: list of words ("word", "prefix*" or "*" for all) tinted with
    accent_color - same semantics as the montazh skills' subs.accent.
    """
    return subtitles.build_pop_subtitles(
        timestamps_json_path, output_ass_path, style=style, highlight_color=highlight_color,
        accent=accent, accent_color=accent_color,
    )


@mcp.tool()
def calculate_acoustic_timeline(
    audio_path: str,
    script_text: str,
    target_scene_count: int = 7,
) -> dict:
    """Calculate scene cut points snapped to real speech pauses.

    Cuts never land mid-word: candidate cuts are snapped to the nearest
    silence centre detected by ffmpeg. Returns scenes with sentence text.
    Works fully offline (ffmpeg only).
    """
    return timeline.calculate_acoustic_timeline(audio_path, script_text, target_scene_count)


@mcp.tool()
def assemble_master_video(
    clips: list[str],
    voiceover: str,
    output_path: str,
    subtitles_ass: str | None = None,
    music: str | None = None,
    music_gain_db: float = -18.0,
) -> dict:
    """Assemble the final master video.

    Normalizes every clip to the master grid, concatenates in order,
    mixes the voiceover (plus optional ducked music bed), loudness-normalizes
    to -14 LUFS and burns the karaoke subtitles. Works offline (ffmpeg only).
    """
    return assemble.assemble_master_video(
        clips,
        voiceover,
        output_path,
        subtitles_ass=subtitles_ass,
        music=music,
        music_gain_db=music_gain_db,
    )


@mcp.tool()
def build_kinetic_video(plan: dict, output_path: str, preview: bool = False) -> dict:
    """Render a vertical kinetic-typography video from pure graphics (no AI generation).

    plan: {"theme": "dark"|"light", "voice": optional audio path,
    "words": optional [{w,s,e}] word timings, "scenes": [{at, kind, ...}],
    "hud": optional overlay over all scenes {at, until, rows: [{label, value}],
    pos: "top"|"bottom", accent_changes: [{at, row, value}]} - a semi-transparent
    dark plate with monospace values; after an accent_change the row's value
    swaps and is accent-highlighted}.
    Scene kinds: words (word-by-word text), title (kicker+headline),
    card (media with caption), big (one huge word), counter (number counts up),
    act (chapter), cta (end card with handle). Modern clean look - no yellow.
    preview=True renders at half resolution.
    """
    from .tools.kinetic import build_kinetic_video as impl

    return impl(plan, output_path, preview=preview)


@mcp.tool()
def qa_verify_video(video_path: str, frames_dir: str | None = None) -> dict:
    """QA-verify a finished master.

    Checks strict resolution (1080x1920), accepted fps, progressive scan,
    audio presence and integrated loudness within +/-2 LUFS of the target.
    Optionally extracts verification frames. Works offline (ffmpeg only).
    """
    return qa.qa_verify_video(video_path, frames_dir)


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
def doctor(check_flow: bool = False) -> dict:
    """One-command environment self-check (same report as the argus-doctor CLI).

    Verifies: python >=3.11; ffmpeg/ffprobe on PATH (or ARGUS_FFMPEG/ARGUS_FFPROBE)
    with a live libass subtitle probe; Node >=18 + npx; engine/node_modules
    (hint: cd engine && npm install); edge-tts installed with a live 1-word
    synthesis probe (15s timeout, retried); playwright+chromium (marked optional
    unless check_flow=True); Gemini key and optional ElevenLabs key presence
    (status only, never an error); OMNIFRAME_OUTPUT_DIR exists/created.
    Returns JSON: {checks, critical_failures, ok}.
    """
    from .doctor import run_checks

    return run_checks(flow=True if check_flow else None)


def main() -> None:
    """Run the MCP server over stdio."""
    banner = (
        f"[ARGUS] Studio v{__version__} АКТИВЕН | 15 тулз | "
        f"{CONFIG.width}x{CONFIG.height}@{CONFIG.fps:.0f} | вывод: {Path(CONFIG.output_dir)}"
    )
    if not CONFIG.gemini_api_key and not CONFIG.elevenlabs_api_key:
        banner += " | API keys: MISSING (generation tools disabled, offline tools OK)"
    print(banner, file=sys.stderr)
    try:
        jobs.cleanup_old_jobs()
    except Exception as exc:  # housekeeping must never stop the server
        print(f"[ARGUS] job cleanup skipped: {exc}", file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
