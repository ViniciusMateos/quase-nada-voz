import base64
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
from logger import log

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


def _token_expirado(token, margem_s=60):
    """O accessToken e um JWT: a validade de verdade esta no exp dele,
    nao no "expires" que o endpoint devolve (esse e do cookie da sessao,
    que dura meses a mais). Token que nao da pra ler conta como valido
    -- na duvida tenta usar, quem derruba e o 401."""
    try:
        corpo = token.split(".")[1]
        corpo += "=" * (-len(corpo) % 4)
        exp = json.loads(base64.urlsafe_b64decode(corpo)).get("exp")
    except Exception:
        return False
    if not isinstance(exp, (int, float)):
        return False
    return exp <= time.time() + margem_s


def _sessao_morreu(data):
    """A sessao ainda existe mas nao consegue mais emitir token novo.
    Nesse estado o endpoint responde 200, manda o token velho vencido e
    avisa no campo "error" (RefreshAccessTokenError)."""
    if data.get("error"):
        return True
    token = data.get("accessToken")
    return not token or _token_expirado(token)


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
    if _sessao_morreu(data):
        log("Sessao salva nao renova mais o token ({}) -- vai precisar entrar de novo".format(
            data.get("error") or "token vencido"))
        return None
    return data["accessToken"], data.get("expires")


# --- aviso dentro da janela do navegador ----------------------------------
# A janela do login abre sem contexto nenhum pro usuario: se o
# preenchimento automatico falhar (a OpenAI muda a tela de login de vez
# em quando), ele fica olhando uma tela de login sem saber que e com ele.
# Esse aviso fica no topo da pagina, sem capturar clique (pointer-events
# none), e e reaplicado a cada volta do laco porque cada navegacao comeca
# uma pagina limpa.
BANNER_SCRIPT = """
(() => {
  const ID = 'qnv-aviso';
  function montar() {
    if (document.getElementById(ID)) return null;
    const caixa = document.createElement('div');
    caixa.id = ID;
    caixa.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;display:flex;justify-content:center;pointer-events:none;padding:14px;font-family:system-ui,Segoe UI,Roboto,sans-serif';
    const pilula = document.createElement('div');
    pilula.id = ID + '-txt';
    pilula.style.cssText = 'max-width:680px;padding:10px 18px;border-radius:14px;background:rgba(18,18,22,.94);color:#eeeef2;font-size:14px;font-weight:500;line-height:1.35;text-align:center;border:1px solid rgba(255,255,255,.18);box-shadow:0 8px 24px rgba(0,0,0,.35)';
    caixa.appendChild(pilula);
    (document.body || document.documentElement).appendChild(caixa);
    return pilula;
  }
  window.__qnvAviso = (texto, tom) => {
    let el = document.getElementById(ID + '-txt') || montar();
    if (!el) return;
    el.textContent = texto;
    el.style.borderColor = tom === 'ok' ? '#14B8A6' : (tom === 'atencao' ? '#F59E0B' : 'rgba(255,255,255,.18)');
    el.style.color = tom === 'ok' ? '#9ff2e6' : '#eeeef2';
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', montar);
  } else {
    montar();
  }
})();
"""

AVISO_ENTRANDO = "Quase Nada Voz: entrando na sua conta, so um instante..."
AVISO_PRONTO = "Pronto, conta conectada! Fechando esta janela..."
FECHA_SOZINHA = " Esta janela fecha sozinha quando terminar."
AVISO_CODIGO = ("A OpenAI mandou um codigo de verificacao pro seu email. Digite ele aqui." + FECHA_SOZINHA)
AVISO_SENHA = "Digite a senha da sua conta aqui." + FECHA_SOZINHA
AVISO_EMAIL = "Entre na sua conta do ChatGPT aqui." + FECHA_SOZINHA
AVISO_MANUAL = "Termine o login nesta janela." + FECHA_SOZINHA
AVISO_CONFIRMANDO = "Quase Nada Voz: confirmando seu login, ja fecho..."
# depois de enviar um campo a tela antiga ainda fica no ar por um
# instante -- sem essa carencia o aviso piscaria "digite a senha"
# justo depois de a senha ter sido enviada
CARENCIA_APOS_ENVIO_S = 3.0

# a tela de login da OpenAI muda de nome de campo de vez em quando (em
# novembro/2026 o #email virou input[name=username]), entao cada campo e
# procurado por uma lista de candidatos em vez de um seletor fixo.
SELETORES_EMAIL = ("input[name=username]", "input[type=email]", "#email", "input[name=email]")
SELETORES_SENHA = ("input[type=password]", "input[name=password]")
SELETORES_CODIGO = ("input[name=code]", "input[autocomplete=one-time-code]")
SELETORES_LINK_SENHA = ('a[href*="password"]', 'button:has-text("senha")', 'a:has-text("senha")',
                        'button:has-text("password")')
SELETORES_ENVIAR = ('button[name="intent"][value="validate"]', "button[type=submit]")

LOGIN_TIMEOUT_S = 180
POLL_MS = 500


class JanelaFechada(Exception):
    """O usuario fechou a janela do navegador."""


def _fechou(e):
    return "closed" in str(e).lower() or "crash" in str(e).lower()


def _aviso(page, texto, tom="info"):
    try:
        page.evaluate("([t, m]) => window.__qnvAviso && window.__qnvAviso(t, m)", [texto, tom])
    except Exception:
        pass  # aviso e conforto, nunca motivo pra derrubar o login


def _primeiro_seletor(page, seletores, espera_s=0):
    """Primeiro seletor da lista que existir na pagina, esperando ate
    espera_s por algum deles."""
    limite = time.time() + espera_s
    while True:
        for sel in seletores:
            try:
                if page.query_selector(sel) is not None:
                    return sel
            except Exception as e:
                if _fechou(e):
                    raise JanelaFechada() from e
        if time.time() >= limite:
            return None
        try:
            page.wait_for_timeout(250)
        except Exception as e:
            if _fechou(e):
                raise JanelaFechada() from e
            raise


def _sessao_viva(dados):
    """Login so conta se a sessao emite token que ainda vale. Sessao que
    responde com token vencido (RefreshAccessTokenError) passava por
    login bem-sucedido e deixava o app sem conseguir ditar."""
    return bool(dados) and bool(dados.get("accessToken")) and not _sessao_morreu(dados)


def _esperar_sessao_ou_campo(page, seletores, timeout_s, aviso=None, tom="info"):
    """Espera o que vier primeiro: a sessao ficar logada, ou um dos
    campos aparecer na tela.

    Os dois tem que ser esperados juntos porque o perfil salvo pode
    redirecionar pro app ja logado DEPOIS do carregamento inicial --
    esperar so pelo campo de email, nesse caso, e esperar por uma tela
    que nunca vem."""
    limite = time.time() + timeout_s
    while True:
        dados = _pedir_sessao(page)
        if _sessao_viva(dados):
            return "sessao", dados
        sel = _primeiro_seletor(page, seletores)
        if sel:
            return "campo", sel
        if time.time() >= limite:
            return None, None
        if aviso:
            _aviso(page, aviso, tom)
        try:
            page.wait_for_timeout(POLL_MS)
        except Exception as e:
            if _fechou(e):
                raise JanelaFechada() from e
            raise


def _enviar_formulario(page, campo):
    """Clica no botao de enviar; sem botao reconhecido, Enter no proprio
    campo (todo formulario de login aceita)."""
    botao = _primeiro_seletor(page, SELETORES_ENVIAR)
    if botao:
        page.click(botao)
    else:
        page.focus(campo)
        page.keyboard.press("Enter")


def _preencher_login(page, email, password):
    """Preenche email e senha, de olho na sessao o tempo todo. Devolve:

    ("sessao", dados) -- ja estava logado (perfil salvo), nada a fazer
    ("enviou", None)  -- senha enviada, e so esperar a sessao aparecer
    ("manual", None)  -- a tela nao bateu com nenhum seletor conhecido;
                         o usuario termina na mao, orientado pelo aviso
    """
    try:
        tipo, valor = _esperar_sessao_ou_campo(page, SELETORES_EMAIL, 20, AVISO_ENTRANDO)
        if tipo == "sessao":
            return "sessao", valor
        if tipo is None:
            return "manual", None

        _human_type(page, valor, email)
        _enviar_formulario(page, valor)

        # a conta pode cair direto na senha ou pedir codigo por email --
        # tendo o link de "continuar com uma senha", prefere a senha
        tipo, valor = _esperar_sessao_ou_campo(
            page, SELETORES_SENHA + SELETORES_CODIGO, 45, AVISO_ENTRANDO)
        if tipo == "sessao":
            return "sessao", valor
        if tipo is None:
            return "manual", None

        if valor in SELETORES_CODIGO:
            link = _primeiro_seletor(page, SELETORES_LINK_SENHA)
            if not link:
                return "manual", None  # so da por codigo: ele pega no email dele
            page.click(link)
            tipo, valor = _esperar_sessao_ou_campo(page, SELETORES_SENHA, 30, AVISO_ENTRANDO)
            if tipo == "sessao":
                return "sessao", valor
            if tipo is None:
                return "manual", None

        _human_pause()
        _human_type(page, valor, password)
        _enviar_formulario(page, valor)
        return "enviou", None
    except JanelaFechada:
        raise
    except Exception as e:
        log(f"Preenchimento automatico do login falhou ({e}) -- o usuario termina na mao")
        return "manual", None


def _pedir_sessao(page):
    """Pergunta pra propria pagina quem esta logado. Deslogado, o
    endpoint responde {} -- entao da pra perguntar desde o primeiro
    instante, sem depender de adivinhar pela URL."""
    try:
        return page.evaluate(
            """async () => {
                try {
                    const r = await fetch('/api/auth/session', {credentials: 'include'});
                    return await r.json();
                } catch (e) { return null; }
            }"""
        )
    except Exception as e:
        if _fechou(e):
            raise JanelaFechada() from e
        return None  # navegacao no meio do evaluate: tenta na proxima volta


def _mensagem_da_tela(page):
    """O que dizer pro usuario, olhando o que esta na tela agora. E isso
    que transforma a espera de "carregando..." em "digite o codigo"."""
    if _primeiro_seletor(page, SELETORES_CODIGO):
        return AVISO_CODIGO, "atencao", SELETORES_CODIGO
    if _primeiro_seletor(page, SELETORES_SENHA):
        return AVISO_SENHA, "atencao", SELETORES_SENHA
    if _primeiro_seletor(page, SELETORES_EMAIL):
        return AVISO_EMAIL, "atencao", SELETORES_EMAIL
    return AVISO_ENTRANDO, "info", None


def _focar(page, seletores):
    """Deixa o cursor no campo que o usuario precisa preencher, pra ele
    so digitar."""
    sel = _primeiro_seletor(page, seletores)
    if not sel:
        return
    try:
        page.focus(sel)
    except Exception:
        pass


def _esperar_sessao(page, timeout_s, carencia_s=0.0):
    """Espera aparecer um accessToken, perguntando de meio em meio
    segundo. E essa a unica prova de que o login terminou: a URL nao
    serve (o ChatGPT passa por telas intermediarias) e esperar a pagina
    do app ficar quieta custava ~6,6s a mais.

    A cada volta o aviso na tela e reescrito (cada navegacao comeca uma
    pagina limpa) com o que falta fazer agora. carencia_s segura o aviso
    em "entrando..." logo depois de um envio, enquanto a tela antiga
    ainda nao saiu."""
    limite = time.time() + timeout_s
    calmo_ate = time.time() + carencia_s
    focado = None
    while True:
        dados = _pedir_sessao(page)
        if _sessao_viva(dados):
            return dados
        if time.time() >= limite:
            return None

        if time.time() < calmo_ate:
            _aviso(page, AVISO_ENTRANDO, "info")
        else:
            texto, tom, campo = _mensagem_da_tela(page)
            _aviso(page, texto, tom)
            # foca uma vez por tela: refocar a cada meio segundo roubaria
            # o cursor do usuario no meio da digitacao
            if campo and campo != focado:
                _focar(page, campo)
                focado = campo
            elif not campo:
                focado = None

        try:
            page.wait_for_timeout(POLL_MS)
        except Exception as e:
            if _fechou(e):
                raise JanelaFechada() from e
            raise


def _lancar_navegador(p, headless=False):
    launch_kwargs = dict(
        user_data_dir=str(PROFILE_DIR),
        headless=headless,
        viewport={"width": 1200, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
    )
    # navegador escolhido nas configuracoes (chrome/msedge) tem
    # prioridade; sem escolha (vazio = "automatico"), tenta o Chrome
    # instalado e depois o Edge (que vem de fabrica em todo Windows) --
    # so cai pro Chromium empacotado do Playwright por ultimo, porque
    # esse exige "playwright install chromium", que um amigo rodando so o
    # .exe nunca vai ter feito.
    escolhido = os.getenv("BROWSER_CHANNEL") or ""
    canais = [escolhido] if escolhido else ["chrome", "msedge"]
    ultimo_erro = None
    for canal in canais:
        try:
            return p.chromium.launch_persistent_context(channel=canal, **launch_kwargs)
        except Exception as e:
            ultimo_erro = e
    if not escolhido:
        try:
            return p.chromium.launch_persistent_context(**launch_kwargs, user_agent=UA)
        except Exception:
            pass
    raise RuntimeError(
        "Não foi possível abrir um navegador para o login. "
        "Instale o Google Chrome ou o Microsoft Edge e tente novamente."
    ) from ultimo_erro


def _sessao_do_perfil(p, timeout_s=20):
    """Le a sessao do perfil salvo. Usado quando o usuario fecha a
    janela do login na mao: o perfil ja ficou logado em disco, nao faz
    sentido obrigar ele a logar tudo de novo.

    Tem que ser COM janela: sem janela o Cloudflare responde 403 ("Um
    momento...") e a sessao nunca aparece (medido). Em compensacao ela
    some sozinha em poucos segundos, e o aviso explica por que voltou."""
    context = _lancar_navegador(p)
    context.add_init_script(STEALTH_INIT_SCRIPT)
    context.add_init_script(BANNER_SCRIPT)
    try:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=30000)
        _aviso(page, AVISO_CONFIRMANDO)
        dados = _esperar_sessao(page, timeout_s=timeout_s, carencia_s=timeout_s)
        return dados, context.cookies()
    finally:
        try:
            context.close()
        except Exception:
            pass


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
        context = _lancar_navegador(p)
        context.add_init_script(STEALTH_INIT_SCRIPT)
        context.add_init_script(BANNER_SCRIPT)

        dados = None
        cookies = None
        fechou_na_mao = False
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            _aviso(page, AVISO_ENTRANDO)

            # o perfil pode estar "logado" numa sessao que nao renova
            # mais o token. Deixando como esta, o ChatGPT abre logado, o
            # formulario de login nunca aparece e nao ha o que fazer --
            # entao desloga aqui pra cair na tela de entrar de verdade.
            inicial = _pedir_sessao(page)
            if inicial and _sessao_morreu(inicial):
                log("Perfil do navegador estava numa sessao morta ({}) -- deslogando pra entrar de novo".format(
                    inicial.get("error") or "token vencido"))
                context.clear_cookies()
                page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
                _aviso(page, AVISO_ENTRANDO)

            estado, dados = _preencher_login(page, email, password)
            if estado != "sessao":
                if estado == "manual":
                    log("Login automatico nao deu conta da tela -- o aviso na janela orienta o usuario")
                    _aviso(page, AVISO_MANUAL, "atencao")
                # dali em diante o proprio aviso vai dizendo o que falta
                # (senha, codigo do email, ou so esperar)
                dados = _esperar_sessao(
                    page, timeout_s=LOGIN_TIMEOUT_S,
                    carencia_s=CARENCIA_APOS_ENVIO_S if estado == "enviou" else 0.0)

            if dados:
                cookies = context.cookies()
                _aviso(page, AVISO_PRONTO, "ok")
                page.wait_for_timeout(700)
            else:
                try:
                    page.screenshot(path=str(DEBUG_SCREENSHOT))
                    log(f"Login nao concluiu a tempo -- screenshot em {DEBUG_SCREENSHOT}")
                except Exception:
                    pass
        except JanelaFechada:
            fechou_na_mao = True
        finally:
            try:
                context.close()
            except Exception:
                pass

        if fechou_na_mao:
            # o perfil precisa estar liberado (contexto acima fechado)
            log("Janela do login fechada na mao -- lendo a sessao do perfil salvo")
            try:
                dados, cookies = _sessao_do_perfil(p)
            except Exception as e:
                log(f"Nao deu pra ler a sessao do perfil: {e}")

    if not _sessao_viva(dados):
        raise RuntimeError(
            "O login não foi concluído. Se você já entrou na conta e fechou a janela, "
            "é só tentar de novo — desta vez entra na hora. Se apareceu captcha ou "
            "verificação extra, complete na janela e tente de novo."
        )

    if cookies:
        _save_json(COOKIE_FILE, cookies)
    _save_json(SESSION_META_FILE, {"email": email})
    return dados["accessToken"], dados.get("expires")


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

    if _sessao_morreu(data):
        # some com o token velho do cache, senao a proxima transcricao
        # ainda tentaria com ele
        invalidate_token_cache()
        return SESSION_EXPIRED if has_credentials else SESSION_NO_CREDENTIALS
    _save_json(TOKEN_CACHE_FILE,
               {"access_token": data["accessToken"], "expires_at": _parse_expires(data.get("expires"))})
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
            # expires_at vem do "expires" do endpoint, que e do cookie e
            # dura meses a mais que o token -- confirma no proprio token
            if not _token_expirado(cache.get("access_token") or ""):
                return cache["access_token"]
            invalidate_token_cache()

        result = _fetch_token_with_saved_cookies()
        if result:
            access_token, expires_iso = result
            _save_json(TOKEN_CACHE_FILE, {"access_token": access_token, "expires_at": _parse_expires(expires_iso)})
            return access_token

    access_token, expires_iso = _login_with_playwright()
    _save_json(TOKEN_CACHE_FILE, {"access_token": access_token, "expires_at": _parse_expires(expires_iso)})
    return access_token
