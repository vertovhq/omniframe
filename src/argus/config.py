"""Runtime configuration for ARGUS.

Everything is environment-driven so the server runs anywhere
without hardcoded accounts, cookies or personal paths.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

_ENV_KEYS = ("ARGUS_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")
_ELEVEN_KEYS = ("ARGUS_ELEVENLABS_API_KEY", "ELEVENLABS_API_KEY")


def _load_dotenv() -> None:
    """Load `.env` from the current directory (best effort)."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def _first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


@dataclass(frozen=True)
class ArgusConfig:
    """Immutable runtime settings resolved once at server start."""

    gemini_api_key: str = ""
    # optional; only needed for voice clones via skills tts.py --provider elevenlabs
    elevenlabs_api_key: str = ""
    veo_provider: str = "api"  # "api" (official, paid) | "flow" (browser session, free credits)
    veo_model: str = "veo-3.1-fast-generate-preview"
    tts_model: str = "gemini-2.5-flash-preview-tts"
    default_voice: str = "Charon"
    width: int = 1080
    height: int = 1920
    fps: float = 30.0
    loudness_target: float = -14.0
    output_dir: Path = field(default_factory=lambda: Path("./output").resolve())
    knowledge_base: Path = field(default_factory=lambda: Path("./KNOWLEDGE_BASE.md").resolve())
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"

    @property
    def resolution(self) -> tuple[int, int]:
        return self.width, self.height


def _resolve_executable(name: str, env_value: str) -> str:
    if env_value:
        return env_value
    found = shutil.which(name)
    return found or name  # let subprocess produce a clear error later


def load_config() -> ArgusConfig:
    """Build the config from environment / `.env` with sane defaults."""
    _load_dotenv()
    api_key = _first_env(*_ENV_KEYS)
    eleven_key = _first_env(*_ELEVEN_KEYS)
    return ArgusConfig(
        gemini_api_key=api_key,
        elevenlabs_api_key=eleven_key,
        veo_provider=os.environ.get("ARGUS_VEO_PROVIDER", "").strip().lower() or ArgusConfig.veo_provider,
        veo_model=os.environ.get("ARGUS_VEO_MODEL", "").strip() or ArgusConfig.veo_model,
        tts_model=os.environ.get("ARGUS_TTS_MODEL", "").strip() or ArgusConfig.tts_model,
        default_voice=os.environ.get("ARGUS_DEFAULT_VOICE", "").strip() or ArgusConfig.default_voice,
        width=int(os.environ.get("ARGUS_WIDTH", "1080")),
        height=int(os.environ.get("ARGUS_HEIGHT", "1920")),
        fps=float(os.environ.get("ARGUS_FPS", "30")),
        loudness_target=float(os.environ.get("ARGUS_LOUDNESS_TARGET", "-14")),
        output_dir=Path(os.environ.get("OMNIFRAME_OUTPUT_DIR", "./output")).resolve(),
        knowledge_base=Path(os.environ.get("ARGUS_KNOWLEDGE_BASE", "./KNOWLEDGE_BASE.md")).resolve(),
        ffmpeg=_resolve_executable("ffmpeg", os.environ.get("ARGUS_FFMPEG", "").strip()),
        ffprobe=_resolve_executable("ffprobe", os.environ.get("ARGUS_FFPROBE", "").strip()),
    )


CONFIG = load_config()
