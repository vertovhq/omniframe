"""Google Flow (Veo) через браузерную сессию: бесплатные кредиты без ручных куки.

Логика:
  flow_login()      — один раз открывает окно, юзер логинится в Google руками,
                      профиль сессии сохраняется на диск (ARGUS_FLOW_PROFILE).
  flow_generate()   — открывает тот же профиль, вбивает промпт в flow.google,
                      ждёт рендер и скачивает готовый клип.

Сессия ровно одна — твоя собственная. Никаких ферм аккаунтов: Google
за мультиакк раздаёт баны пачкой. Селекторы UI собраны в SELECTORS —
когда Google поменяет вёрстку, чинится в одном месте.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path

from ..config import CONFIG
from .. import __version__

FLOW_URL = "https://flow.google/"

# Централизованные селекторы flow.google (чинить только здесь).
# Порядок = приоритет: первое найденное используется.
SELECTORS = {
    "prompt_input": [
        "textarea[aria-label*='rompt']",
        "div[contenteditable='true'][role='textbox']",
        "textarea",
    ],
    "submit": [
        "button[aria-label*='ubmit']",
        "button[aria-label*='reate']",
        "button[aria-label*=' Arrow']",
        "button[type='submit']",
    ],
    "download": [
        "button[aria-label*='ownload']",
        "a[aria-label*='ownload']",
        "button[download]",
    ],
}

LOGIN_HINTS = ("accounts.google.com", "ServiceLogin", "signmaxerr")


def _profile_dir(profile: str | None) -> Path:
    raw = (profile or os.environ.get("ARGUS_FLOW_PROFILE", "")).strip()
    if not raw:
        raw = str(Path.home() / ".argus" / "flow_profile")
    return Path(raw).expanduser()


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright не установлен: pip install 'argus-studio[flow]' "
            "&& playwright install chromium"
        )
    return sync_playwright()


def _is_logged_in(page) -> bool:
    url = page.url
    if any(h in url for h in ("accounts.google.com", "ServiceLogin")):
        return False
    for sel in SELECTORS["prompt_input"]:
        try:
            if page.locator(sel).first.is_visible(timeout=1500):
                return True
        except Exception:
            continue
    return False


def flow_login(profile: str | None = None, max_wait_s: float = 420.0) -> dict:
    """Логин-визард: открыть окно, дождаться ручного входа, сохранить профиль."""
    prof = _profile_dir(profile)
    prof.parent.mkdir(parents=True, exist_ok=True)
    with _playwright() as pw:
        browser = pw.chromium.launch_persistent_context(
            str(prof), headless=False, viewport={"width": 1280, "height": 900}
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(FLOW_URL, wait_until="domcontentloaded", timeout=60000)
        print("В окне браузера войди в Google и дождись загрузки Flow...")
        started = time.monotonic()
        logged = False
        while time.monotonic() - started < max_wait_s:
            try:
                if _is_logged_in(page):
                    logged = True
                    break
            except Exception:
                pass  # страница могла перезагружаться
            time.sleep(2)
        browser.close()
    if not logged:
        raise TimeoutError("Вход не зафиксирован — запусти flow_login ещё раз")
    return {"profile": str(prof), "status": "logged in", "url": FLOW_URL}


def _first_visible(page, names):
    for name in names:
        for sel in SELECTORS[name]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=1800):
                    return loc
            except Exception:
                continue
    return None


def _download_via_button(page, out: Path, max_wait_s: float) -> bool:
    btn = _first_visible(page, ["download"])
    if btn is None:
        return False
    with page.expect_download(timeout=max_wait_s * 1000) as dl_info:
        btn.click()
    dl_info.value.save_as(str(out))
    return True


def _download_via_blob(page, video_src: str, out: Path) -> bool:
    if not video_src:
        return False
    b64 = page.evaluate(
        """async (src) => {
            const r = await fetch(src);
            const buf = await r.arrayBuffer();
            let bin = '';
            const bytes = new Uint8Array(buf);
            for (let i = 0; i < bytes.length; i += 0x8000)
                bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
            return btoa(bin);
        }""",
        video_src,
    )
    out.write_bytes(base64.b64decode(b64))
    return True


def flow_generate(
    prompt: str,
    output_path: str,
    *,
    profile: str | None = None,
    max_wait_s: float = 900.0,
) -> dict:
    """Сгенерировать клип через браузерную сессию Flow (бесплатные кредиты)."""
    prof = _profile_dir(profile)
    if not prof.exists():
        raise RuntimeError(
            "Нет сохранённой сессии Flow. Один раз запусти flow_login "
            "(MCP-тулза flow_login) и войди в Google в открывшемся окне."
        )
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    with _playwright() as pw:
        browser = pw.chromium.launch_persistent_context(
            str(prof), headless=True, viewport={"width": 1280, "height": 900}
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(FLOW_URL, wait_until="domcontentloaded", timeout=60000)
        if not _is_logged_in(page):
            browser.close()
            raise RuntimeError(
                "Сессия Flow протухла — запусти flow_login и перелогинься."
            )

        box = _first_visible(page, ["prompt_input"])
        if box is None:
            browser.close()
            raise RuntimeError("Не нашёл поле промпта flow.google — Google поменял UI? Поправь SELECTORS['prompt_input'].")
        box.click()
        box.fill(prompt)
        time.sleep(0.5)

        submit = _first_visible(page, ["submit"])
        if submit is not None:
            submit.click()
        else:
            box.press("Enter")

        # Ждём появления нового <video> (рендер 1–3 мин; кредиты списываются сразу)
        video_src = ""
        deadline = started + max_wait_s
        while time.monotonic() < deadline:
            try:
                videos = page.locator("video")
                for i in range(videos.count()):
                    src = videos.nth(i).get_attribute("src") or ""
                    if src:
                        video_src = src
                        break
                if video_src:
                    break
            except Exception:
                pass
            time.sleep(5)
        if not video_src:
            browser.close()
            raise TimeoutError(
                f"Рендер не завершился за {max_wait_s:.0f}с — проверь кредиты Flow или запусти ещё раз."
            )
        time.sleep(3)  # даём видео догрузиться

        saved = _download_via_blob(page, video_src, out) or _download_via_button(page, out, 120)
        browser.close()

    if not saved or not out.exists() or out.stat().st_size < 10_000:
        raise RuntimeError("Не удалось скачать клип (маленький/пустой файл). Попробуй ещё раз.")

    return {
        "engine": f"ARGUS {__version__}",
        "output": str(out),
        "provider": "flow",
        "elapsed_s": round(time.monotonic() - started, 1),
    }
