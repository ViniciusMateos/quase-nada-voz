import json
import os
import random
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

BASE_DIR = Path(__file__).parent
COOKIE_FILE = BASE_DIR / "session_cookies.json"
TOKEN_CACHE_FILE = BASE_DIR / "token_cache.json"
PROFILE_DIR = BASE_DIR / ".browser_profile"
DEBUG_SCREENSHOT = BASE_DIR / "login_debug.png"

LOGIN_URL = "https://chatgpt.com/auth/login"
SESSION_URL = "https://chatgpt.com/api/auth/session"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"

STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
"""


def _human_pause(a=0.3, b=0.9):
    time.sleep(random.uniform(a, b))


def _human_type(page, selector, text):
    page.click(selector)
    _human_pause(0.15, 0.4)
    page.type(selector, text, delay=random.randint(70, 160))
    _human_pause(0.2, 0.5)


def _save_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def _parse_expires(expires_iso):
    if not expires_iso:
        return time.time() + 55 * 60
    try:
        return datetime.fromisoformat(expires_iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return time.time() + 55 * 60


def _fetch_token_with_saved_cookies():
    cookies = _load_json(COOKIE_FILE)
    if not cookies:
        return None
    jar = {c["name"]: c["value"] for c in cookies}
    try:
        resp = requests.get(SESSION_URL, cookies=jar, headers={"user-agent": UA}, timeout=15)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    token = data.get("accessToken")
    if not token:
        return None
    return token, data.get("expires")


def _wait_until_authenticated(page, timeout_s=180):
    """Espera a pagina sair de /auth (login concluido). Da tempo pro usuario
    intervir manualmente na janela (captcha, verificacao extra etc.) se a
    automacao nao conseguir concluir sozinha."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if "chatgpt.com" in page.url and "/auth" not in page.url and "log-in" not in page.url:
                return
            page.wait_for_timeout(1000)
        except Exception as e:
            if "closed" in str(e).lower():
                raise RuntimeError(
                    "A janela do navegador foi fechada antes do login terminar. "
                    "Rode de novo e deixe a janela aberta ate ela voltar pro chatgpt.com."
                )
            raise
    raise RuntimeError(
        "Login nao foi concluido a tempo. Se apareceu captcha ou verificacao extra, "
        "complete manualmente na janela do navegador e rode de novo."
    )


def _login_with_playwright():
    email = os.getenv("OPENAI_EMAIL")
    password = os.getenv("OPENAI_PASSWORD")
    if not email or not password:
        raise RuntimeError("OPENAI_EMAIL / OPENAI_PASSWORD nao configurados no .env")

    with sync_playwright() as p:
        launch_kwargs = dict(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1200, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            context = p.chromium.launch_persistent_context(channel="chrome", **launch_kwargs)
        except Exception:
            context = p.chromium.launch_persistent_context(**launch_kwargs, user_agent=UA)

        context.add_init_script(STEALTH_INIT_SCRIPT)

        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
            _human_pause(0.5, 1.2)

            already_logged_in = "chatgpt.com" in page.url and "/auth" not in page.url
            if not already_logged_in:
                try:
                    _human_type(page, "#email", email)
                    page.click("button[type=submit]")

                    page.wait_for_selector("input[name=code], input[type=password]", timeout=45000)
                    _human_pause()

                    if page.query_selector("input[name=code]") is not None:
                        link = page.query_selector('a[href*="password"]')
                        if link is not None:
                            link.click()
                            page.wait_for_selector("input[type=password]", timeout=30000)
                            _human_pause()

                    if page.query_selector("input[type=password]") is not None:
                        _human_type(page, "input[type=password]", password)
                        submit = page.query_selector('button[name="intent"][value="validate"]')
                        if submit is not None:
                            submit.click()
                        else:
                            page.click("input[type=password] ~ * button[type=submit]")
                except Exception as e:
                    print(f"[auth] Preenchimento automatico falhou ({e}). "
                          f"Complete o login manualmente na janela que abriu.")

                try:
                    _wait_until_authenticated(page)
                except Exception:
                    try:
                        page.screenshot(path=str(DEBUG_SCREENSHOT))
                        print(f"[auth] Screenshot salvo em {DEBUG_SCREENSHOT}")
                    except Exception:
                        pass
                    raise
                page.wait_for_load_state("networkidle")

            token_json = None
            for _ in range(3):
                token_json = page.evaluate(
                    """async () => {
                        const r = await fetch('/api/auth/session', {credentials: 'include'});
                        return await r.json();
                    }"""
                )
                if token_json and token_json.get("accessToken"):
                    break
                page.wait_for_timeout(1000)

            cookies = context.cookies()
            _save_json(COOKIE_FILE, cookies)
        finally:
            context.close()

    if not token_json or not token_json.get("accessToken"):
        raise RuntimeError(f"Login concluiu mas nao veio accessToken: {token_json}")

    return token_json["accessToken"], token_json.get("expires")


def get_access_token(force_relogin=False):
    """Retorna um access token valido pra usar no header Authorization.
    Renova sozinho via cookie salvo; se o cookie tambem expirou, refaz o
    login completo (abre o navegador, usa OPENAI_EMAIL/OPENAI_PASSWORD)."""
    now = time.time()

    if not force_relogin:
        cache = _load_json(TOKEN_CACHE_FILE)
        if cache and cache.get("expires_at", 0) - 60 > now:
            return cache["access_token"]

        result = _fetch_token_with_saved_cookies()
        if result:
            access_token, expires_iso = result
            _save_json(TOKEN_CACHE_FILE, {"access_token": access_token, "expires_at": _parse_expires(expires_iso)})
            return access_token

    access_token, expires_iso = _login_with_playwright()
    _save_json(TOKEN_CACHE_FILE, {"access_token": access_token, "expires_at": _parse_expires(expires_iso)})
    return access_token
