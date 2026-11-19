"""Caption helpers: word timings in, clean and grouped words out (design §8, §9 step 2).

Word dicts use the keys `{"word", "start", "end"}` (seconds). Files written by the
voice and watch tools use `{w, s, e}`; `parse_words` accepts both.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

PHRASE_MAX_WORDS = 4
PHRASE_MAX_CHARS = 26
PHRASE_GAP_S = 0.45


def parse_words(data: Any) -> list[dict]:
    """Normalise a words payload to `[{word, start, end}]`.

    Accepts a list, or a dict holding the list under `words` / `timestamps`. Items may be
    `{word, start, end}` or `{w, s, e}`. Entries with an empty word are skipped.
    """
    if isinstance(data, dict):
        data = data.get("words") or data.get("timestamps") or []
    words = []
    for item in data:
        word = str(item.get("word") or item.get("w") or "").strip()
        if not word:
            continue
        words.append({
            "word": word,
            "start": float(item.get("start", item.get("s"))),
            "end": float(item.get("end", item.get("e"))),
        })
    if not words:
        raise ValueError("no usable {word,start,end} entries in timestamps file")
    return words


def load_words(timestamps_json_path: str | Path) -> list[dict]:
    """Read a words file (`words.json`) and return `[{word, start, end}]`."""
    return parse_words(json.loads(Path(timestamps_json_path).read_text(encoding="utf-8")))


def clean_word_timings(words: list[dict], min_dur: float = 0.06) -> tuple[list[dict], int]:
    """Make word timings strictly monotonic and non-overlapping.

    Words keep their spoken order. A run of words whose starts collapse onto
    each other (aligner glitch: "СОРОК ПЯТЬ ТЫСЯЧ" all at 48.1s) gets its
    span split evenly; any remaining overlap is pushed forward.
    Returns (words, n_fixed).
    """
    ws = [dict(w) for w in words]
    fixed = 0
    i = 0
    while i < len(ws):
        j = i + 1
        while j < len(ws) and ws[j]["start"] < ws[j - 1]["end"] - 1e-3:
            j += 1
        if j - i > 1:
            a = min(w["start"] for w in ws[i:j])
            b = max(max(w["end"] for w in ws[i:j]), a + min_dur * (j - i))
            if j < len(ws) and ws[j]["start"] > a + min_dur * (j - i):
                b = min(b, ws[j]["start"])
            step = (b - a) / (j - i)
            for k in range(i, j):
                ws[k]["start"] = a + step * (k - i)
                ws[k]["end"] = a + step * (k - i + 1)
            fixed += j - i
        i = j
    prev_end = 0.0
    for w in ws:
        if w["start"] < prev_end - 1e-3:
            w["start"] = prev_end
            fixed += 1
        if w["end"] < w["start"] + min_dur:
            w["end"] = w["start"] + min_dur
        prev_end = w["end"]
    return ws, fixed


def group_phrases(words: list[dict], max_words: int = PHRASE_MAX_WORDS,
                  max_chars: int = PHRASE_MAX_CHARS, gap_s: float = PHRASE_GAP_S) -> list[list[dict]]:
    """Split words into short on-screen lines: break on sentence end, pause,
    word or character budget."""
    lines: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        if cur:
            chars = sum(len(x["word"]) + 1 for x in cur) + len(w["word"])
            pause = w["start"] - cur[-1]["end"]
            if (len(cur) >= max_words or chars > max_chars or pause > gap_s
                    or cur[-1]["word"][-1:] in ".!?…"):
                lines.append(cur)
                cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    return lines


_TOKEN_STRIP = re.compile(r"[\W_]+", re.UNICODE)


def _token(word: str) -> str:
    """Same rule as `normalizeToken` in engine/src/text.tsx: lower case, letters and digits only."""
    return _TOKEN_STRIP.sub("", word.lower())


def resolve_cues(cues: Mapping[str, Any], words: Sequence[Mapping[str, Any]] | None) -> tuple[dict[str, float], list[str]]:
    """Plan cues as seconds on the output timeline, plus errors for cues that cannot be placed.

    A number is kept. A word cue (`word`, `nth`, `offset`; see `plan.WordCue`) is the start of the
    `nth` place where its words are spoken in a row, plus `offset` (never before 0). `words` are
    `{w, s, e}` on the output timeline, as `render_video` loads them for the captions.
    """
    out: dict[str, float] = {}
    errors: list[str] = []
    tokens = [_token(str(w["w"])) for w in words or []]
    for name, cue in cues.items():
        if isinstance(cue, (int, float)):
            out[name] = round(float(cue), 3)
            continue
        query = [_token(t.rstrip("*")) + ("*" if t.endswith("*") else "") for t in str(_cue_field(cue, "word")).split()]
        query = [q for q in query if q.strip("*")]
        nth = int(_cue_field(cue, "nth"))
        offset = float(_cue_field(cue, "offset"))
        if not query:
            errors.append(f"cues.{name}: {_cue_field(cue, 'word')!r} has no letters or digits to look for")
            continue
        starts = [
            i for i in range(len(tokens) - len(query) + 1)
            if all(tokens[i + k].startswith(q[:-1]) if q.endswith("*") else tokens[i + k] == q for k, q in enumerate(query))
        ]
        if len(starts) < nth:
            heard = f"it is spoken {len(starts)} time(s)" if starts else "it is not in the words"
            errors.append(
                f"cues.{name}: cannot find occurrence {nth} of {_cue_field(cue, 'word')!r} in captions.words ({heard}); "
                "check the spelling against the voice words file"
            )
            continue
        out[name] = round(max(0.0, float(words[starts[nth - 1]]["s"]) + offset), 3)  # type: ignore[index]
    return out, errors


def _cue_field(cue: Any, name: str) -> Any:
    return cue.get(name, 1 if name == "nth" else 0.0) if isinstance(cue, Mapping) else getattr(cue, name)


def _clip_field(clip: Any, name: str) -> Any:
    """Read `src`/`at`/`in`/`out` from a dict or from a plan `Clip` (its `in` is `in_`)."""
    if isinstance(clip, Mapping):
        return clip.get(name)
    return getattr(clip, "in_" if name == "in" else name, None)


def _same_file(a: str | Path, b: str | Path) -> bool:
    if str(a) == str(b):
        return True
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return False


def remap_words_to_clips(words: Iterable[Mapping[str, Any]], clips: Sequence[Any],
                         source: str | Path) -> list[dict]:
    """Move words from source-file time to output time for the kept ranges.

    For each clip whose `src` is the `source` file, keep the words whose midpoint lies in
    `[in, out]` (`in` defaults to 0, a missing `out` means "to the end") and shift them by
    `at - in`. A word that straddles a cut is kept when more than half of it is inside,
    and its edges are clamped to the range. The same source range used by two clips
    yields its words twice. Result is sorted by start time.
    """
    ws = [dict(w) for w in words]
    out: list[dict] = []
    for clip in clips:
        src = _clip_field(clip, "src")
        if src is None or not _same_file(src, source):
            continue
        at = float(_clip_field(clip, "at") or 0.0)
        lo = float(_clip_field(clip, "in") or 0.0)
        hi_raw = _clip_field(clip, "out")
        hi = float("inf") if hi_raw is None else float(hi_raw)
        shift = at - lo
        for w in ws:
            start, end = float(w["start"]), float(w["end"])
            if not lo <= (start + end) / 2 <= hi:
                continue
            item = dict(w)
            item["start"] = max(start, lo) + shift
            item["end"] = max(min(end, hi), max(start, lo)) + shift
            out.append(item)
    out.sort(key=lambda w: (w["start"], w["end"]))
    return out
