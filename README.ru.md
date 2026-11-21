# ARGUS

**MCP-студия вертикального видео: два пути контента — ИИ-генерация и чистая графика.**

ARGUS собирает ролики 1080×1920 из чего угодно: клипы Veo 3.1 через официальный API или
через твою браузерную сессию Google Flow (бесплатные кредиты, без ручных куки), либо
вообще без ИИ — вертикальная кинетическая типографика рендерится локальным движком
(Remotion) из JSON-плана. Плюс озвучка с таймингами слов, сабы по этим таймингам,
рендер, QA и экспорт — всё как MCP-инструменты для ИИ-ассистента.

```
                    ┌─▶ generate_veo_clip (api | flow) ──┐
текст/промпты ──┤                                        ├──▶ render_video ──▶ QA ──▶ export_package
скрипт ─────────┴─▶ графические сцены в плане ───────────┘      ▲   (9:16 / 16:9, −14 LUFS)
озвучка ──▶ synthesize_voiceover (аудио + тайминги слов) ───────┘
```

## Инструменты

| Инструмент | Что делает | Офлайн |
|---|---|---|
| `studio_guide` | Рабочий метод, доступные тулзы и провайдеры, сохранённые предпочтения пользователя. Вызывается первым в каждой сессии | ✅ |
| `watch_video` | Смены кадра, контактные листы, слова транскрипта и звуковые события видео — картинками и таймкодами | ✅ |
| `get_frames` | Точные кадры видео картинками (можно с кропом) | ✅ |
| `voice_options` | Доступные сейчас голоса и провайдеры | ✅ |
| `synthesize_voiceover` | Озвучка + тайминги слов (edge-tts, Gemini, ElevenLabs), мастеринг −14 LUFS | edge-tts нужна сеть |
| `generate_veo_clip` | Клип Veo 3.1. `provider="api"` — официальный API (платно, у Veo нет бесплатного тарифа API); `provider="flow"` — твоя сессия flow.google (бесплатные кредиты, `flow_login` один раз) | — |
| `flow_login` | Одноразовый логин-визард Flow: открывает окно, ты логинишься, профиль сессии сохраняется. Куки руками не копируются. Один свой аккаунт — за фермы аккаунтов банят | — |
| `render_video` | План → stills, preview или final в 9:16 / 16:9: графические сцены, клипы с футажом, сабы, музыка и звуки из плана | ✅ |
| `job_status` | Состояние и результат долгой операции, вернувшей `job_id` | ✅ |
| `qa_verify_video` | Технические проверки (размер, fps, громкость, пики, чёрные провалы, длины дорожек) + кадры для просмотра | ✅ |
| `export_package` | Финальная папка: видео, обложки, `post.md` | ✅ |
| `calculate_beat_grid` | Темп и сетка битов музыкального трека | ✅ |
| `search_sfx`, `download_sfx` | Звуковые эффекты Freesound CC0 | — |
| `run_script` | Запуск твоих Python-скриптов из `scripts/` | ✅ |
| `learn_and_record_memory` | Сохраняет постоянное предпочтение пользователя; `studio_guide` отдаёт его в следующих сессиях | ✅ |
| `doctor` | Самопроверка окружения одной командой (`argus-doctor` или MCP): python/ffmpeg/Node/engine/numpy/Pillow/опционально faster-whisper, edge-tts, playwright, ключи/папка вывода — таблица ✓/✗/⚠, под каждым ✗ точная команда установки | ✅ |

## Установка

Требования: Python 3.11+, ffmpeg в PATH. Для кинетики — Node.js 18+.

```bash
git clone <url репозитория argus-studio>   # или скачай архив и распакуй
cd argus-studio
pip install -e ".[dev,pretty,voice]"  # voice = edge-tts (бесплатная озвучка); + flow → pip install -e ".[flow,pretty]"
playwright install chromium           # только для provider="flow"
cd engine && npm install --no-audit --no-fund && cd ..   # только для кинетики
cp .env.example .env                  # ключ Gemini для api-режима/TTS
```

## Подключение ассистента

```json
{
  "mcpServers": {
    "argus": {
      "command": "argus-studio",
      "env": { "ARGUS_GEMINI_API_KEY": "ключ", "ARGUS_VEO_PROVIDER": "api" }
    }
  }
}
```

Больше вариантов — в [`examples/mcp-config.example.json`](examples/mcp-config.example.json).

Пример запроса ассистенту: «Собери вертикальный ролик: скрипт такой-то, без Veo —
одна графика, тёмная тема, озвучь Charon, сабы clean, QA в конце» — ассистент
сам разложит задачу по тулзам.

## Оба пути контента

**Через Veo** — кинематографичные сгенерированные кадры:

```text
generate_veo_clip(prompt="ночной город, неон, дождь", output_path="out/c1.mp4")
generate_veo_clip(prompt="...", output_path="out/c2.mp4", provider="flow")  # халява Flow
```

**Через графику** (без ИИ, локально, бесплатно):

```text
render_video(project="demo", mode="stills", times=[1, 4, 8], plan={
  "version": 2,
  "format": "9:16",
  "style": "dark",
  "hud": {                                   # оверлей поверх всех сцен
    "at": 0.5, "until": 5.5,                 # интервал жизни плашки, сек
    "rows": [
      {"label": "ДО СРОКА", "value": "365 ДНЕЙ"},
      {"label": "РАБОЧИЕ", "value": "0/100"}
    ],
    "pos": "top",                            # top | bottom
    "accent_changes": [                      # замена значения + акцентная подсветка
      {"at": 3.0, "row": 1, "value": "20/100"}
    ]
  },
  "scenes": [
    {"at": 0.0, "kind": "words", "text": "стоп скроллить это сейчас"},
    {"at": 2.5, "kind": "title", "kicker": "глава 1", "text": "что тут происходит"},
    {"at": 5.0, "kind": "counter", "value": 87, "suffix": "%", "sub": "не доходят до конца"},
    {"at": 6.5, "kind": "cta", "text": "забирай бесплатно", "handle": "@you"}
  ],
  "audio": {"voice": {"src": "audio/voice.mp3"}}
})
```

Посмотри stills, затем рендери `mode="preview"` и `mode="final"`. Больше планов — в
[`examples/plans/`](examples/plans).

`hud` — игровой оверлей уровня плана (не сцена): полупрозрачная тёмная плашка
с моноширинными значениями живёт в своём интервале поверх всех сцен, не мешая
им. По `accent_changes` значение строки заменяется и подсвечивается акцентом
(прогресс «0/100» → «20/100»).

Дальше одинаково: `synthesize_voiceover` → `render_video` (stills, preview, final;
сабы берутся из блока `captions` плана) → `qa_verify_video` → `export_package`.

## Структура репо

```
argus-studio/
├── src/argus/          MCP-сервер и инструменты
├── engine/             Remotion-движок кинетической графики (npm install)
├── tests/              офлайн-тесты (pytest)
└── examples/           конфиги MCP, примеры
```

## Честные примечания

- Veo через API платный (~$0.40/сек качество, ~$0.10–0.12/сек Fast); бесплатного API-тарифа нет.
  Халявный путь — `provider="flow"` со своими кредитами flow.google; он зависит от их UI —
  селекторы вынесены в одно место в `src/argus/tools/flow_browser.py`.
- Сабы рисует движок из блока `captions` плана; файлов `.ass` больше нет.
- Промпты уходят в Veo как есть — никаких обходов правил контента.

## English

See [README.md](README.md).

## Лицензия

ARGUS — бесплатный открытый проект под лицензией [AGPL-3.0](LICENSE). Автор: VertovHQ.
Коммерческая лицензия: напишите VertovHQ.

Рендер использует [Remotion](https://www.remotion.dev) со своей лицензией:
https://www.remotion.dev/license
