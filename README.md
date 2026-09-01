# Quase Nada Voz

Ditado por voz via hotkey: aperte, fale, solte — o texto transcrito é colado automaticamente onde estiver o cursor.

## Setup (já feito nesta pasta)

- `venv/` criado com as dependências de `requirements.txt` instaladas.
- Chromium do Playwright já baixado (`playwright install chromium` já foi executado).
- `.env` criado a partir de `.env.example` — falta só colocar seu email e senha de verdade.

## Login automático (sem copiar token na mão)

Em vez de pegar o token manualmente no DevTools, agora o script loga sozinho:

1. Você coloca seu email e senha do ChatGPT em `.env` (`OPENAI_EMAIL` / `OPENAI_PASSWORD`).
2. Na primeira vez (ou sempre que a sessão expirar de vez), o `auth.py` abre uma janela do Chrome, preenche o login sozinho e extrai a sessão.
3. Essa sessão fica salva em `session_cookies.json` e `token_cache.json` (na própria pasta do projeto, fora do git). Enquanto ela for válida, o script renova o token de acesso automaticamente via requisição HTTP simples — **sem abrir navegador**.
4. Quando o token de acesso expira (geralmente ~1h), ele é renovado sozinho a partir do cookie salvo.
5. Quando o próprio cookie de sessão expira (dura bem mais, semanas), o script detecta (a chamada volta vazia / a API responde 401), abre o navegador de novo e refaz o login sozinho com o email/senha do `.env`.

Ou seja: você só vê a janela do navegador abrir raramente — no primeiro uso, e depois só quando a sessão realmente expirar.

### Se aparecer captcha ou verificação extra

A OpenAI muda a tela de login de vez em quando (às vezes pede um código por email antes de deixar entrar com senha — o script já clica em "Continuar com uma senha" sozinho nesse caso). Se algo não bater (captcha, verificação nova etc.), a janela do navegador fica aberta por até 3 minutos esperando — é só completar o login manualmente nela que o script continua sozinho a partir daí. Se travar, um screenshot é salvo em `login_debug.png` pra facilitar o diagnóstico.

Detalhes técnicos pra reduzir a chance de bloqueio por automação:
- Usa o **Chrome de verdade instalado no Windows** (não o Chromium de teste que vem com o Playwright).
- Digita o email/senha simulando digitação humana (com pausas), em vez de preencher instantâneo.

### Importante

- **Senha em texto plano no `.env`**: é o jeito mais simples de automatizar, mas fica salva sem criptografia no seu disco. `.env` já está no `.gitignore`, então não vai parar em nenhum repositório — mas qualquer processo com acesso ao seu usuário Windows consegue ler o arquivo. Se isso for um problema, me avisa que dá pra trocar por outra estratégia (ex: gerenciador de credenciais do Windows).
- Isso automatiza login numa conta OpenAI usando os endpoints internos do site (não é uma API oficial) — pode violar os termos de uso deles, e pode quebrar quando a OpenAI mudar o layout do login. Uso por sua conta e risco.
- `session_cookies.json`, `token_cache.json` e `.browser_profile/` também têm dados sensíveis (equivalentes a estar logado) — já estão no `.gitignore`.

## Rodar

Dê duplo clique em `start.bat`, ou:

```
venv\Scripts\activate
python quase_nada_voz.py
```

Tem dois jeitos de usar o hotkey (**F9** por padrão, ou o que estiver em `HOTKEY` no `.env`):

- **Segurar e soltar**: grava enquanto a tecla está pressionada, transcreve e cola ao soltar.
- **Toque rápido**: aperte e solte rápido (menos de ~0,35s) para travar a gravação ligada — toque de novo pra parar e transcrever.

Um ícone aparece na bandeja do sistema (perto do relógio, pode estar escondido nos "ícones ocultos" na primeira vez): cinza quando ocioso, vermelho enquanto grava. Clique com o botão direito nele para sair.

Os beeps dizem o que aconteceu:

- **800Hz ao apertar** — comecou a gravar.
- **1500Hz agudo** — transcreveu e colou o texto.
- **400Hz grave** — gravou, mas nao veio fala reconhecivel (microfone mudo ou baixo demais). Nao e problema de sessao, entao nao abre navegador.
- **Dois beeps de 500Hz** — erro. O motivo fica em `quase_nada_voz.log`, na pasta do projeto.

O navegador so abre quando a API responde 401/403 de verdade — e mesmo assim ele tenta primeiro renovar a sessao pelo cookie salvo, sem abrir nada.

## Iniciar com o Windows

Já foi criado um atalho em `shell:startup` apontando para `start.bat` — o script sobe automaticamente no login, com uma janela de terminal visível. Para desativar, apague `QuaseNadaVoz.lnk` da pasta Startup (`Win+R` → `shell:startup`).

## Configurações (`.env`)

- `OPENAI_EMAIL` / `OPENAI_PASSWORD` — obrigatórios, login da sua conta ChatGPT (login direto por senha, não Google/Microsoft).
- `OAI_DEVICE_ID` — opcional, tem um valor padrão.
- `HOTKEY` — opcional (padrão `F9`). Outras opções: `F10`, `F13`, `CAPSLOCK`, `RCONTROL`, `SCROLLLOCK`.

## Observações

- Usa o endpoint interno `chatgpt.com/backend-api/transcribe` (não oficial/documentado) — pode mudar ou parar de funcionar sem aviso.
- Cada gravação fica registrada em `quase_nada_voz.log` (duração, pico do áudio, erro) — útil porque a janela do terminal some junto com o processo.
- O microfone padrão do Windows é usado para gravação; troque o dispositivo padrão do sistema se quiser usar outro.
