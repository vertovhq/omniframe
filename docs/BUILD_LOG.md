# ARGUS v2 — build log (Kiroween 2026)

A factual record of how ARGUS v2 was built in Kiro. It is the source for the Medium
article and for the submission's "how Kiro was used" answer. Facts only, no marketing.

## How the work is split

- **Planning:** Claude Opus 5.5 in Kiro wrote the spec (`.kiro/specs/argus-v2`:
  requirements, design, tasks), steering (`.kiro/steering`: product, tech, engine), the
  studio guide for the model, and two hooks (pytest after every spec task, engine
  typecheck on save) in one planning session.
- **Why v2:** v1 grew feature by feature into creative "gates" (30% story-overlap and
  30% digit-density rules, slop-word lists, a 150-line rule book), a renderer limited to
  dark/light vertical frames, and tools that returned file paths the model could not see.
  Output was generic "neuroslop". v2 makes the model the director and ARGUS its eyes,
  ears and hands.
- **Coding:** Claude Sonnet 5.5 (high effort) for core tasks; Claude Haiku 5.5 (max
  effort) planned for well-specified, test-covered tasks (QA, export, scripts, CI, docs
  drafts). Opus only plans and audits from diffs and reports, to save credits.

## Credits

| Date | Tasks | Model / effort | Credits used / total |
|---|---|---|---|
| (author fills) | 1–8, 9 started | Sonnet 5.5 high | 330 / 4000 |

## Entry template

```
## Task N — <title> (<date>, <model> <effort>)
- Built: <what changed, 1–2 lines>
- Bugs & fixes: <symptom> → <cause> → <fix>   (or "none")
- Kiro: <which Kiro feature helped, concretely: spec task/steering rule/hook caught X/MCP/autopilot>   (or "none")
- Verified: <command or manual check> → <result>
- Credits: <author fills>
```

## Entries

## Task 1 — Setup

_To be filled retroactively from git and .kiro/specs/argus-v2/task5–7.md._

## Task 2 — Remove creative gates

_To be filled retroactively from git and .kiro/specs/argus-v2/task5–7.md._

## Task 3 — Studio guide and preferences

_To be filled retroactively from git and .kiro/specs/argus-v2/task5–7.md._

## Task 4 — Images to the model + jobs

_To be filled retroactively from git and .kiro/specs/argus-v2/task5–7.md._

## Task 5 — watch_video and get_frames

_To be filled retroactively from git and .kiro/specs/argus-v2/task5–7.md._

## Task 6 — Voice v2

_To be filled retroactively from git and .kiro/specs/argus-v2/task5–7.md._

## Task 7 — Plan model v2

_To be filled retroactively from git and .kiro/specs/argus-v2/task5–7.md._

## Task 8 — Engine: formats and style tokens

_To be filled retroactively from git and .kiro/specs/argus-v2/task5–7.md._

## Task 9 — Engine: captions and audio (2026-11-16, Sonnet 5.5)
- Built: `captions.tsx` (word and phrase modes, accent words, upper/center/lower inside the safe area, plate), `audio.tsx` (voice, music with ducking and 0.25 s ramps, fades, `audio.sfx`); `sfx.ts` no longer adds automatic effects.
- Bugs & fixes: none in the engine. Two of my own check assertions were wrong (float equality on a ramp value; a phrase-length case that fits the character budget), and a light-theme still had a scene under the caption → fixed the checks and the test plan.
- Kiro: steering `engine.md` (layer order, "no automatic sound effects", no hardcoded sizes) set the design of the two components; `get_diagnostics` gave quick type errors while editing.
- Verified: `tsc --noEmit` exit 0; `node test-baseline/check_audio_captions.mjs` (ducking, fades, phrase grouping, accent matching, SFX list) passed; 34 stills rendered (both modes, 9:16 and 16:9, upper/center/lower, plate, light theme), 10 of them looked at by eye (the rest are unchecked); pytest 189 passed, 1 skipped.
- Credits: <author fills>
