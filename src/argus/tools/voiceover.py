"""Studio voiceover: Gemini native TTS + Hollywood radio mastering chain.

Chain (the signature "Charon" radio sound):
  60 Hz highpass -> 110 Hz body EQ -> 3.2 kHz presence EQ
  -> compressor -> loudnorm to the ARGUS target (default -14 LUFS).
"""

from __future__ import annotations

import wave
from pathlib import Path

from ..config import CONFIG
from ..ffmpeg import run_ffmpeg, stream_info, temp_sibling

AVAILABLE_VOICES = (
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
)


def mastering_chain(loudness_target: float) -> str:
    """The fixed ARGUS radio-master ffmpeg filter chain."""
    return ",".join([
        "highpass=f=60",
        "equalizer=f=110:t=q:w=1:g=2",
        "equalizer=f=3200:t=q:w=2:g=3",
        "acompressor=threshold=-18dB:ratio=3:attack=10:release=120",
        f"loudnorm=I={loudness_target}:TP=-1.5:LRA=11",
    ])


def _pcm_to_wav(pcm: bytes, wav_path: Path, rate: int = 24000) -> None:
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)


def synthesize_voiceover(
    text: str,
    *,
    voice_name: str | None = None,
    output_path: str | None = None,
    master: bool = True,
) -> dict:
    """Synthesize a masculine radio-grade voiceover and master it to MP3."""
    if not text.strip():
        raise ValueError("empty text")

    if not CONFIG.gemini_api_key:
        raise RuntimeError(
            "No Gemini API key configured. Copy .env.example to .env and set "
            "ARGUS_GEMINI_API_KEY."
        )
    from google import genai
    from google.genai import types

    voice = (voice_name or CONFIG.default_voice).strip()
    client = genai.Client(api_key=CONFIG.gemini_api_key)
    response = client.models.generate_content(
        model=CONFIG.tts_model,
        contents=text.strip(),
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        ),
    )

    parts = response.candidates[0].content.parts
    pcm = next((p.inline_data.data for p in parts if p.inline_data), None)
    if not pcm:
        raise RuntimeError("TTS returned no audio data")

    out = Path(output_path).resolve() if output_path \
        else (CONFIG.output_dir / "voiceover").with_suffix(".mp3")
    out.parent.mkdir(parents=True, exist_ok=True)

    raw_wav = temp_sibling(out, ".raw.wav")
    try:
        _pcm_to_wav(pcm, raw_wav)
        if master:
            run_ffmpeg([
                "-i", str(raw_wav),
                "-af", mastering_chain(CONFIG.loudness_target),
                "-ar", "48000", "-ac", "2",
                "-codec:a", "libmp3lame", "-b:a", "320k",
                str(out),
            ])
        else:
            run_ffmpeg(["-i", str(raw_wav), "-ar", "48000", "-ac", "2", str(out)])
    finally:
        raw_wav.unlink(missing_ok=True)

    return {
        "output": str(out),
        "voice": voice,
        "mastered": master,
        "duration": round(stream_info(out).duration, 3),
    }
