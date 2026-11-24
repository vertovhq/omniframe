"""Task 20.10 items 10, 11 and 13: a voice says which project it wrote into, empty voice lists explain
themselves, and a rate-limited ElevenLabs call is retried before it fails.

Offline: no ElevenLabs key is set, so no request leaves the machine; the job queue, urlopen and sleep are fakes.
"""

from __future__ import annotations

import dataclasses
import io
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniframe import jobs, project  # noqa: E402
from omniframe.config import CONFIG  # noqa: E402
from omniframe.tools import voiceover  # noqa: E402


@pytest.fixture(autouse=True)
def voice_project_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = dataclasses.replace(CONFIG, output_dir=tmp_path / "out", elevenlabs_api_key="", gemini_api_key="")
    for module in (jobs, project, voiceover):
        monkeypatch.setattr(module, "CONFIG", cfg)
    monkeypatch.delenv("OMNIFRAME_TTS_PROVIDER", raising=False)


# ------------------------------------------------------------------ item 10: the project a voice writes into

def test_holdings_ignore_empty_folders_and_voices_but_list_finished_work() -> None:
    root = project.project_dir("kiroween")
    assert project.project_holdings("kiroween") == []
    (root / "audio" / "vo1.mp3").write_bytes(b"x")  # a second voice of the same video is normal
    assert project.project_holdings("kiroween") == []
    (root / "plan.json").write_text("{}", encoding="utf-8")
    (root / "renders" / "preview.mp4").write_bytes(b"x")
    assert project.project_holdings("kiroween") == ["plan.json", "renders"]


def test_holdings_check_creates_no_folder() -> None:
    assert project.project_holdings("never-made") == []
    assert not (project.CONFIG.output_dir / "projects" / "never-made").exists()


def test_voice_call_hands_the_holdings_to_the_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(voiceover, "resolve_provider", lambda name: None)  # provider choice is not under test here
    root = project.project_dir("omniframe-demo")
    (root / "plan.json").write_text("{}", encoding="utf-8")
    seen: dict = {}

    def fake_job(kind: str, payload: dict, wait_s: float = 0.0) -> dict:
        seen.update(kind=kind, payload=payload)
        return {"job_id": "voiceover-test"}

    monkeypatch.setattr(jobs, "run_or_detach", fake_job)
    voiceover.synthesize_voiceover("Hello there.", "omniframe-demo")
    assert seen["kind"] == "voiceover"
    assert seen["payload"]["project"] == "omniframe-demo"
    assert seen["payload"]["project_holds"] == ["plan.json"]


# ------------------------------------------------------------------ item 11: empty lists name the cause

def test_permission_error_names_the_permission_and_the_http_code() -> None:
    body = (
        '{"detail": {"status": "missing_permissions", "message": "The API key you used is missing the '
        'permission voices_read to execute this operation."}}'
    )
    text = voiceover._eleven_error_text(401, "GET", "/v2/voices", body)
    assert text.startswith("ElevenLabs HTTP 401 on GET /v2/voices")
    assert "voices_read" in text
    assert "dashboard" in text


def test_query_that_matches_nothing_says_why_and_reports_no_error() -> None:
    result = voiceover.voice_options(language="ru", gender="male", query="narrator")
    assert not result.get("errors")
    assert any("no voice matches" in note for note in result.get("notes", []))


# ------------------------------------------------------------------ item 13: rate limits are retried

def _too_many(headers: dict | None) -> urllib.error.HTTPError:
    body = b'{"detail": {"status": "too_many_requests", "message": "slow down"}}'
    return urllib.error.HTTPError("https://api.elevenlabs.io/v2/voices", 429, "Too Many Requests", headers or {}, io.BytesIO(body))


def test_rate_limit_is_retried_with_the_server_wait_then_named(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    sleeps: list[float] = []

    def refuse(request, timeout=None):
        calls.append(request.full_url)
        raise _too_many({"Retry-After": "3"})

    monkeypatch.setattr(voiceover.urllib.request, "urlopen", refuse)
    monkeypatch.setattr(voiceover.time, "sleep", sleeps.append)
    with pytest.raises(RuntimeError) as err:
        voiceover._eleven_json("GET", "/v2/voices")
    assert len(calls) == voiceover.ELEVEN_RATE_RETRIES + 1
    assert sleeps == [3] * voiceover.ELEVEN_RATE_RETRIES
    assert "rate limited, wait 3 s" in str(err.value)


def test_rate_limit_without_retry_after_doubles_the_pause(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    def refuse(request, timeout=None):
        raise _too_many(None)

    monkeypatch.setattr(voiceover.urllib.request, "urlopen", refuse)
    monkeypatch.setattr(voiceover.time, "sleep", sleeps.append)
    # four attempts; the pauses between them are 2, 4 and 8 s, and the message names the last wait (16 s)
    with pytest.raises(RuntimeError, match="rate limited, wait 16 s"):
        voiceover._eleven_json("GET", "/v2/voices")
    assert sleeps == [2, 4, 8]


def test_a_retry_that_succeeds_returns_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = [_too_many({"Retry-After": "1"}), io.BytesIO(b'{"voices": []}')]
    sleeps: list[float] = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def flaky(request, timeout=None):
        item = answers.pop(0)
        if isinstance(item, urllib.error.HTTPError):
            raise item
        return Response(item.getvalue())

    monkeypatch.setattr(voiceover.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(voiceover.time, "sleep", sleeps.append)
    assert voiceover._eleven_json("GET", "/v2/voices") == {"voices": []}
    assert sleeps == [1]
