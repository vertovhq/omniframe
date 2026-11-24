# Third-party notices

This file lists code, libraries and media that OmniFrame uses, copies or adapts, and the license that
applies to each. The OmniFrame license itself is in [LICENSE](LICENSE).

## video-shotcraft (Apache License 2.0)

- Project: https://github.com/vincentwei1021/video-shotcraft
- License text: [licenses/video-shotcraft-LICENSE](licenses/video-shotcraft-LICENSE). It is the
  upstream `LICENSE` file from the `main` branch, copied byte for byte.
- NOTICE file: video-shotcraft has no NOTICE file in its repository (checked on the `main` branch),
  so there is no NOTICE text to carry over.
- Use in OmniFrame:
  - `src/omniframe/tools/sfx.py` is ported from the video-shotcraft Freesound sourcing code.
  - `src/omniframe/tools/beats.py` uses the beat-grid method of video-shotcraft.
  - OmniFrame changed both files. The changes are in this repository's git history.

## Remotion (its own license)

- Project: https://www.remotion.dev. OmniFrame uses the `remotion` and `@remotion/*` packages, pinned to
  4.0.540 in `engine/package.json`.
- Remotion is not open source under a standard license. Its license is at
  https://www.remotion.dev/license. Its free license covers individuals and companies of up to three
  people. Larger organizations need a Remotion company license.
- Remotion packages are installed from npm by `install.sh`, `install.ps1` or `npm install` in
  `engine/`. OmniFrame does not copy Remotion source code.

## Inter (SIL Open Font License 1.1)

- Files: `engine/public/fonts/InterDisplay-*.otf`, used by the render engine.

## Sample media in `examples/media/`

- `moving-shapes-8s.mp4`: an 8 second clip generated for this repository with ffmpeg's lavfi sources
  (a gradient and moving boxes). It contains no third-party material and has no sound track.
- The sample voiceover is not stored in the repository. Running the example makes it with OmniFrame
  (`synthesize_voiceover`). Without an ElevenLabs key, that uses Microsoft's Edge read-aloud voices,
  which remain subject to Microsoft's terms for that service.

## Downloaded at run time, not bundled

- Freesound sound effects (`search_sfx`, `download_sfx`). CC0 sounds need no attribution. CC-BY
  sounds need attribution, which `download_sfx` writes to `FREESOUND-CREDITS.md` in the project.
- Python packages (`mcp`, `google-genai`, `numpy`, `Pillow`, `edge-tts`, `faster-whisper`)
  and their licenses, as listed in `pyproject.toml`.
- ffmpeg and ffprobe, which OmniFrame calls as external programs.
