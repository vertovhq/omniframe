# ARGUS

**MCP-сервер, который превращает промпты в готовые вертикальные видео.**

ARGUS — продакшн-конвейер для вирусного контента 1080×1920: генерация клипов Veo,
озвучка студийного качества, покадровые караоке-сабы, резка сцен по паузам,
сборка мастера и автопроверка качества — всё в одном MCP-сервере, которым управляет ИИ-ассистент.

```
промпт ──▶ клипы Veo 3.1 ──┐
скрипт ──▶ TTS-озвучка ────┼──▶ assemble_master_video ──▶ qa_verify_video ──▶ master.mp4
голос  ──▶ караоке-сабы ───┘      (1080×1920, -14 LUFS)
```

## Инструменты

| Инструмент | Что делает | Нужен API? |
|---|---|---|
| `generate_veo_clip` | Клип Veo 3.1, по умолчанию 9:16, поллит до готовности | Ключ Gemini |
| `synthesize_voiceover` | Нативный TTS Gemini (по умолчанию Charon) + мастеринг: 60 Hz HPF → EQ 110/3.2 kHz → компрессор → loudnorm −14 LUFS | Ключ Gemini |
| `calculate_acoustic_timeline` | Точки склеек, привязанные к реальным паузам в речи — никогда не режет посреди слова | только ffmpeg |
| `build_pop_subtitles` | Покадровые караоке-сабы Safe Pop (`.ass`): 1 слово на кадр, жёлтый хайлайт #FFE066, уровень глаз (MarginV 420), жирная обводка, без плашки | ничего |
| `assemble_master_video` | Склейка клипов → микс озвучки + музыкальная подложка → loudnorm → вшивание сабов | только ffmpeg |
| `qa_verify_video` | Строгие проверки разрешения/fps/развёртки, замер LUFS, контрольные кадры | только ffmpeg |
| `learn_and_record_memory` | Запись проверенных уроков в `KNOWLEDGE_BASE.md` | ничего |

Инструменты генерации работают через **официальный Gemini API** — один ключ,
никаких куки, никакой браузерной автоматизации, никаких махинаций с аккаунтами.

## Требования

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/download.html) в PATH
- Бесплатный ключ Gemini API ([aistudio.google.com/apikey](https://aistudio.google.com/apikey)) — только для двух генерирующих инструментов

## Установка

```bash
git clone https://github.com/your-name/argus-studio
cd argus-studio
pip install -e .
```

Настройка:

```bash
cp .env.example .env   # впиши свой ARGUS_GEMINI_API_KEY
```

## Подключение ассистента

Добавь в конфиг MCP-клиента (Claude Desktop, ZCode, …):

```json
{
  "mcpServers": {
    "argus-studio": {
      "command": "argus-studio",
      "env": { "ARGUS_GEMINI_API_KEY": "твой-ключ" }
    }
  }
}
```

Другие варианты (python -m, своя папка вывода) — в [`examples/mcp-config.example.json`](examples/mcp-config.example.json).

## Типовой конвейер

Просто попроси ассистента:

> Сгенерируй клип 9:16 про ночной город под дождём, озвучь глубоким мужским голосом,
> добавь караоке-сабы из examples/timestamps.example.json, собери и проверь.

…или дергай шаги напрямую:

```text
generate_veo_clip(prompt="ночной город, дождь, неон, кинематографично", output_path="out/clip1.mp4")
synthesize_voiceover(text="Это нельзя было показывать…", voice_name="Charon")
calculate_acoustic_timeline(audio_path="out/voiceover.mp3", script_text="…", target_scene_count=7)
build_pop_subtitles(timestamps_json_path="out/timestamps.json", output_ass_path="out/subs.ass")
assemble_master_video(clips=["out/clip1.mp4"], voiceover="out/voiceover.mp3",
                      subtitles_ass="out/subs.ass", output_path="out/master.mp4")
qa_verify_video(video_path="out/master.mp4", frames_dir="out/qa")
```

## Настройки

Всё живёт в `.env` (шаблон — [.env.example](.env.example)): модели, формат мастера
(по умолчанию 1080×1920@30), целевая громкость, папка вывода, пути к ffmpeg.
Ключ читается из `ARGUS_GEMINI_API_KEY` (или `GEMINI_API_KEY` / `GOOGLE_API_KEY`).

## Честные примечания

- Рендер Veo занимает 1–3 минуты на клип; инструмент ждёт до `max_wait_s`.
- Промпты уходят в Veo **как написаны**. Никаких скрытых переписываний для обхода
  правил контента — такие трюки приводят к бану аккаунта, поэтому промпты держим чистыми.
- `qa_verify_video` строгий специально: ровно 1080×1920, стандартный fps,
  прогрессивная развёртка, ±2 LUFS вокруг −14.

## Лицензия

[MIT](LICENSE)
