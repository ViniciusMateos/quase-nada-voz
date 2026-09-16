import json
import os
import random
import shutil
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

import paths

load_dotenv(paths.DATA_DIR / ".env")

COOKIE_FILE = paths.DATA_DIR / "session_cookies.json"
TOKEN_CACHE_FILE = paths.DATA_DIR / "token_cache.json"
PROFILE_DIR = paths.DATA_DIR / ".browser_profile"
DEBUG_SCREENSHOT = paths.DATA_DIR / "login_debug.png"
# de qual email e a sessao salva (cookies + perfil do navegador). Trocar o
# email no painel nao apaga mais a sessao na hora -- um erro de digitacao
# derrubaria o login a toa. Em vez disso, email diferente do da sessao
# conta como "expirada" e o proximo login limpa a sessao antiga.
SESSION_META_FILE = paths.DATA_DIR / "session_meta.json"

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

    if _session_email_mismatch(email):
        # outra conta: o perfil do navegador ainda esta logado na antiga e
        # o login "ja logado" pegaria o token dela
        shutil.rmtree(PROFILE_DIR, ignore_errors=True)
        for f in (COOKIE_FILE, TOKEN_CACHE_FILE):
            f.unlink(missing_ok=True)

    with sync_playwright() as p:
        launch_kwargs = dict(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1200, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = None
        last_error = None
        # navegador escolhido nas configuracoes (chrome/msedge) tem
        # prioridade; sem escolha (vazio = "automatico"), tenta o Chrome
        # instalado e depois o Edge (que vem de fabrica em todo Windows)
        # -- so cai pro Chromium empacotado do Playwright por ultimo,
        # porque esse exige "playwright install chromium", que um amigo
        # rodando so o .exe nunca vai ter feito.
        chosen = os.getenv("BROWSER_CHANNEL") or ""
        channels = [chosen] if chosen else ["chrome", "msedge"]
        for channel in channels:
            try:
                context = p.chromium.launch_persistent_context(channel=channel, **launch_kwargs)
                break
            except Exception as e:
                last_error = e
        if context is None and not chosen:
            try:
                context = p.chromium.launch_persistent_context(**launch_kwargs, user_agent=UA)
            except Exception:
                pass
        if context is None:
            raise RuntimeError(
                "Não foi possível abrir um navegador para o login. "
                "Instale o Google Chrome ou o Microsoft Edge e tente novamente."
            ) from last_error

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
            _save_json(SESSION_META_FILE, {"email": email})
        finally:
            context.close()

    if not token_json or not token_json.get("accessToken"):
        raise RuntimeError(f"Login concluiu mas nao veio accessToken: {token_json}")

    return token_json["accessToken"], token_json.get("expires")


SESSION_OK = "ok"
SESSION_EXPIRED = "expired"
SESSION_NO_CREDENTIALS = "no_credentials"
SESSION_OFFLINE = "offline"


def check_session():
    """Diz se da pra transcrever agora, SEM nunca abrir navegador:
    - "ok": a sessao salva vale (e o token em cache e renovado de brinde)
    - "no_credentials": sem sessao valida e sem email/senha pra entrar
    - "expired": tem email/senha, mas a sessao salva nao vale mais --
      precisa entrar de novo pela aba Conta
    - "offline": nao deu pra falar com o chatgpt.com (rede caiu, bloqueio
      temporario). Isso nao prova nada sobre a conta."""
    has_credentials = bool(os.getenv("OPENAI_EMAIL") and os.getenv("OPENAI_PASSWORD"))
    cookies = _load_json(COOKIE_FILE)
    if not cookies:
        return SESSION_EXPIRED if has_credentials else SESSION_NO_CREDENTIALS
    if has_credentials and _session_email_mismatch(os.getenv("OPENAI_EMAIL")):
        return SESSION_EXPIRED

    jar = {c["name"]: c["value"] for c in cookies if "name" in c and "value" in c}
    try:
        resp = requests.get(SESSION_URL, cookies=jar, headers={"user-agent": UA}, timeout=15)
    except requests.RequestException:
        return SESSION_OFFLINE
    # sem login o endpoint responde 200 com {} -- outro status (desafio do
    # Cloudflare, erro 5xx) nao diz se a sessao morreu
    if resp.status_code != 200:
        return SESSION_OFFLINE
    try:
        data = resp.json()
    except ValueError:
        return SESSION_OFFLINE

    token = data.get("accessToken")
    if not token:
        return SESSION_EXPIRED if has_credentials else SESSION_NO_CREDENTIALS
    _save_json(TOKEN_CACHE_FILE, {"access_token": token, "expires_at": _parse_expires(data.get("expires"))})
    return SESSION_OK


def _session_email_mismatch(email):
    meta = _load_json(SESSION_META_FILE) or {}
    saved = (meta.get("email") or "").strip().lower()
    return bool(saved and email and saved != email.strip().lower())


def remember_session_email(email):
    """Sessoes feitas antes de existir o session_meta.json nao sabem de
    qual email sao. Chamado com o email ANTIGO logo antes de trocar, pra
    essa associacao nao se perder."""
    if email and COOKIE_FILE.exists() and not SESSION_META_FILE.exists():
        _save_json(SESSION_META_FILE, {"email": email.strip()})


def invalidate_token_cache():
    """Descarta o access token salvo pra forcar renovacao pelo cookie."""
    try:
        TOKEN_CACHE_FILE.unlink()
    except FileNotFoundError:
        pass


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
