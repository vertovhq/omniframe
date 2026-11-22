# Sample media

Files for the judge quickstart in the main [README](../../README.md).

- `moving-shapes-8s.mp4`: an 8 second clip, 720x1280 (9:16), 30 fps, with no sound track. It was
  generated for this repository with ffmpeg's lavfi sources: a moving gradient and five moving boxes.
  It contains no third-party material.
- `sample-voiceover.txt`: the text of the sample voiceover. ARGUS voices it when you run the example
  (`synthesize_voiceover`). No audio file is stored in the repository.

For production-quality voice, add your ElevenLabs API key to .env (ELEVENLABS_API_KEY). Without a key ARGUS falls back to a free voice so the example still runs.
