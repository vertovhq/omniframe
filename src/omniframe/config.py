"""Runtime configuration for OmniFrame.

Everything is environment-driven so the server runs anywhere
without hardcoded accounts, cookies or personal paths.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ._compat import mirror_legacy_env, omniframe_home

_ENV_KEYS = ("OMNIFRAME_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")
_ELEVEN_KEYS = ("OMNIFRAME_ELEVENLABS_API_KEY", "ELEVENLABS_API_KEY")

# src/omniframe/config.py -> parents[2] is the repository root (where .env lives).
REPO_ROOT = Path(__file__).resolve().parents[2]


def find_env_file(cwd: Path | None = None, repo_root: Path | None = None) -> Path | None:
    """First existing env file, in order: `OMNIFRAME_ENV_FILE`, `./.env`, `<repo>/.env`, `~/.omniframe/.env`.

    An `OMNIFRAME_ENV_FILE` that points at a missing file is skipped, so the lookup
    continues with the next candidate.
    """
    candidates: list[Path] = []
    explicit = os.environ.get("OMNIFRAME_ENV_FILE", "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.append((cwd or Path.cwd()) / ".env")
    candidates.append((repo_root or REPO_ROOT) / ".env")
    # package installs (uvx, Kiro Power) have no repository: keys go in ~/.omniframe/.env
    candidates.append(omniframe_home() / ".env")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _load_dotenv() -> None:
    """Load the file from `find_env_file()` (best effort).

    Values already set in the process environment win over the file, because
    python-dotenv does not override existing variables by default.
    """
    path = find_env_file()
    if path is None:
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(path)
    mirror_legacy_env()  # a `.env` that still uses ARGUS_* names


def _first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


@dataclass(frozen=True)
class OmniFrameConfig:
    """Immutable runtime settings resolved once at server start."""

    gemini_api_key: str = ""
    # optional; only needed for the ElevenLabs voice provider
    elevenlabs_api_key: str = ""
    # Model id is empty by default: OmniFrame takes the newest model the key lists (tools/model_catalog.py).
    tts_model: str = ""  # Gemini TTS model id
    default_voice: str = "Charon"
    width: int = 1080
    height: int = 1920
    fps: float = 30.0
    loudness_target: float = -14.0
    output_dir: Path = field(default_factory=lambda: Path("./output").resolve())
    knowledge_base: Path = field(default_factory=lambda: Path("./KNOWLEDGE_BASE.md").resolve())
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    whisper_model: str = "small"  # faster-whisper model size, used by watch_video transcripts
    eleven_model: str = ""  # ElevenLabs TTS model id; empty = newest text-to-speech model the key lists
    render_concurrency: int = 0  # Remotion render workers; 0 = let the renderer pick
    scripts_dir: Path = field(default_factory=lambda: _default_scripts_dir())

    @property
    def resolution(self) -> tuple[int, int]:
        return self.width, self.height


def _default_scripts_dir() -> Path:
    return omniframe_home() / "scripts"


def _resolve_executable(name: str, env_value: str) -> str:
    if env_value:
        return env_value
    found = shutil.which(name)
    return found or name  # let subprocess produce a clear error later


def _int_env(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    value = int(raw)
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    return value


def load_config() -> OmniFrameConfig:
    """Build the config from environment / `.env` with sane defaults."""
    _load_dotenv()
    api_key = _first_env(*_ENV_KEYS)
    eleven_key = _first_env(*_ELEVEN_KEYS)
    scripts_raw = os.environ.get("OMNIFRAME_SCRIPTS_DIR", "").strip()
    return OmniFrameConfig(
        gemini_api_key=api_key,
        elevenlabs_api_key=eleven_key,
        tts_model=os.environ.get("OMNIFRAME_TTS_MODEL", "").strip() or OmniFrameConfig.tts_model,
        default_voice=os.environ.get("OMNIFRAME_DEFAULT_VOICE", "").strip() or OmniFrameConfig.default_voice,
        width=int(os.environ.get("OMNIFRAME_WIDTH", "1080")),
        height=int(os.environ.get("OMNIFRAME_HEIGHT", "1920")),
        fps=float(os.environ.get("OMNIFRAME_FPS", "30")),
        loudness_target=float(os.environ.get("OMNIFRAME_LOUDNESS_TARGET", "-14")),
        output_dir=Path(os.environ.get("OMNIFRAME_OUTPUT_DIR", "./output")).resolve(),
        knowledge_base=Path(os.environ.get("OMNIFRAME_KNOWLEDGE_BASE", "./KNOWLEDGE_BASE.md")).resolve(),
        ffmpeg=_resolve_executable("ffmpeg", os.environ.get("OMNIFRAME_FFMPEG", "").strip()),
        ffprobe=_resolve_executable("ffprobe", os.environ.get("OMNIFRAME_FFPROBE", "").strip()),
        whisper_model=os.environ.get("OMNIFRAME_WHISPER_MODEL", "").strip() or OmniFrameConfig.whisper_model,
        eleven_model=os.environ.get("OMNIFRAME_ELEVEN_MODEL", "").strip() or OmniFrameConfig.eleven_model,
        render_concurrency=_int_env("OMNIFRAME_RENDER_CONCURRENCY", OmniFrameConfig.render_concurrency, 0),
        scripts_dir=(
            Path(scripts_raw).expanduser().resolve()
            if scripts_raw
            else _default_scripts_dir()
        ),
    )


CONFIG = load_config()
