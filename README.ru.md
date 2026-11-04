# ARGUS

**MCP-студия вертикального видео: два пути контента — ИИ-генерация и чистая графика.**

ARGUS собирает ролики 1080×1920 из чего угодно: клипы Veo 3.1 через официальный API или
через твою браузерную сессию Google Flow (бесплатные кредиты, без ручных куки), либо
вообще без ИИ — вертикальная кинетическая типографика рендерится локальным движком
(Remotion) из JSON-плана. Плюс озвучка с клоном голоса, покадровые сабы, резка сцен
по паузам, сборка мастера и QA — всё как MCP-инструменты для ИИ-ассистента.

В монорепу входят три монтажных скилла («Эпизод», «Мани», «Эссе»), которые повторяют
личные стили монтажа по plan.json — см. [`skills/`](skills/README.md).

```
                    ┌─▶ generate_veo_clip (api | flow) ──┐
текст/промпты ──┤                                        ├──▶ assemble ──▶ QA ──▶ мастер
скрипт ─────────┴─▶ build_kinetic_video (графика) ──────┘      ▲        (1080×1920, −14 LUFS)
озвучка ──▶ TTS / клон голоса ──▶ таймлайн ──▶ сабы ───────────┘
```

## Инструменты (9)

| Инструмент | Что делает | Офлайн |
|---|---|---|
| `generate_veo_clip` | Клип Veo 3.1. `provider="api"` — официальный API (платно, у Veo нет бесплатного тарифа API); `provider="flow"` — твоя сессия flow.google (бесплатные кредиты, `flow_login` один раз) | — |
| `flow_login` | Одноразовый логин-визард Flow: открывает окно, ты логинишься, профиль сессии сохраняется. Куки руками не копируются. Один свой аккаунт — за фермы аккаунтов банят | — |
| `build_kinetic_video` | **Вертикальное видео из чистой графики**: типографика слово-за-словом, карточки, счётчики, главы, плашки (chip), CTA. Автозвук: воуши на склейках, попы/удары, музыкальная подложка. Темы dark/light | ✅ |
| `synthesize_voiceover` | Gemini TTS + радиомастеринг (−14 LUFS). Клоны голоса — `tts.py` в скиллах | — |
| `build_pop_subtitles` | Караоке-сабы .ass. Стили: `clean` (белый, дефолт), `outline`, `pop` (легаси-жёлтый по запросу) | ✅ |
| `calculate_acoustic_timeline` | Склейки прилипают к реальным паузам в речи | ✅ |
| `assemble_master_video` | Склейка клипов + микс голоса и музыки + вшивание сабов | ✅ |
| `qa_verify_video` | Строгие проверки: 1080×1920, fps, развёртка, LUFS ±2 | ✅ |
| `learn_and_record_memory` | Уроки продакшна в KNOWLEDGE_BASE.md | ✅ |

## Установка

Требования: Python 3.11+, ffmpeg в PATH. Для кинетики — Node.js 18+.

```bash
git clone https://github.com/your-name/argus-studio
cd argus-studio
pip install -e ".[dev,pretty]"       # + flow → pip install -e ".[flow,pretty]"
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
build_kinetic_video(plan={
  "theme": "dark",
  "voice": "out/voiceover.mp3",
  "scenes": [
    {"at": 0.0, "kind": "words", "text": "стоп скроллить это сейчас"},
    {"at": 2.5, "kind": "title", "kicker": "глава 1", "text": "что тут происходит"},
    {"at": 5.0, "kind": "counter", "value": 87, "suffix": "%", "sub": "не доходят до конца"},
    {"at": 6.5, "kind": "cta", "text": "забирай бесплатно", "handle": "@you"}
  ]
}, output_path="out/kinetic.mp4")
```

Дальше одинаково: `synthesize_voiceover` → `calculate_acoustic_timeline` →
`build_pop_subtitles(style="clean")` → `assemble_master_video` → `qa_verify_video`.

## Структура репо

```
argus-studio/
├── src/argus/          MCP-сервер и инструменты
├── engine/             Remotion-движок кинетической графики (npm install)
├── skills/             три монтажных скилла + tts.py с клоном голоса
├── tests/              офлайн-тесты (pytest)
└── examples/           конфиги MCP, примеры
```

## Честные примечания

- Veo через API платный (~$0.40/сек качество, ~$0.10–0.12/сек Fast); бесплатного API-тарифа нет.
  Халявный путь — `provider="flow"` со своими кредитами flow.google; он зависит от их UI —
  селекторы вынесены в одно место в `src/argus/tools/flow_browser.py`.
- Субтитры по умолчанию — стиль `clean` (белый). Жёлтый `pop` остался для обратной совместимости.
- Промпты уходят в Veo как есть — никаких обходов правил контента.
- В `skills/` звуки платных подписок и личные материалы не входят — клади свои (см. skills/README.md).

## English

See [README.md](README.md).

## Лицензия

[MIT](LICENSE)
