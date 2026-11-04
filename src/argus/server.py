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

from . import __version__
from .config import CONFIG
from .tools import assemble, memory, qa, subtitles, timeline

mcp = MCPServer(
    "Argus",
    instructions=(
        "Production studio for vertical videos (1080x1920). Two content paths: "
        "AI clips via generate_veo_clip (provider 'api' with ARGUS_GEMINI_API_KEY, "
        "or 'flow' - the user's own Google Flow browser session, run flow_login "
        "once) OR pure graphics via build_kinetic_video (no AI, offline). "
        "Typical pipeline: generate_veo_clip or build_kinetic_video (xN) -> "
        "synthesize_voiceover -> calculate_acoustic_timeline -> build_pop_subtitles "
        "-> assemble_master_video -> qa_verify_video. Timeline, subtitles, kinetic, "
        "assembly, QA and memory work fully offline with ffmpeg."
    ),
)


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
    voice_name: str | None = None,
    output_path: str | None = None,
    master: bool = True,
) -> dict:
    """Synthesize a studio-grade voiceover via Gemini native TTS.

    Default voice Charon (deep masculine narrator). With master=True the track
    gets the radio chain: 60 Hz highpass, 110 Hz body EQ, 3.2 kHz presence EQ,
    compressor and loudnorm to -14 LUFS. Requires ARGUS_GEMINI_API_KEY.
    """
    from .tools.voiceover import synthesize_voiceover as impl

    return impl(text, voice_name=voice_name, output_path=output_path, master=master)


@mcp.tool()
def build_pop_subtitles(
    timestamps_json_path: str,
    output_ass_path: str,
    style: str = "clean",
    highlight_color: str = "#FFE066",
) -> dict:
    """Generate frame-accurate karaoke subtitles (.ass).

    Input: JSON list of {word, start, end} (seconds). One word per cue,
    centered at eye level (MarginV 420), bold wide font.
    Styles: "clean" (default - white text, soft shadow, modern), "outline"
    (white with thick black outline, classic shorts), "pop" (legacy yellow
    highlight #FFE066). highlight_color applies to the "pop" style.
    """
    return subtitles.build_pop_subtitles(
        timestamps_json_path, output_ass_path, style=style, highlight_color=highlight_color
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
    "words": optional [{w,s,e}] word timings, "scenes": [{at, kind, ...}]}.
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
def learn_and_record_memory(
    lesson_title: str,
    user_directive: str,
    technical_rule: str,
    knowledge_base_path: str | None = None,
) -> dict:
    """Append a verified production lesson to KNOWLEDGE_BASE.md.

    Use it after every confirmed user correction or invariant so the
    studio retains the rule across sessions.
    """
    return memory.learn_and_record_memory(lesson_title, user_directive, technical_rule)


def main() -> None:
    """Run the MCP server over stdio."""
    banner = (
        f"ARGUS v{__version__} | {CONFIG.width}x{CONFIG.height}@{CONFIG.fps:.0f} "
        f"| output: {Path(CONFIG.output_dir)}"
    )
    if not CONFIG.gemini_api_key:
        banner += " | API key: MISSING (generation tools disabled, offline tools OK)"
    print(banner, file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
