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

Dê duplo clique no atalho **"Quase Nada Voz"** na área de trabalho (roda em segundo plano, sem janela de terminal), ou:

```
venv\Scripts\activate
python app.py
```

`start.bat` faz a mesma coisa mas com o terminal visível (útil pra ver logs/erros).

Tem dois jeitos de usar o hotkey (**F9** por padrão, configurável no painel — veja abaixo):

- **Segurar e soltar**: grava enquanto a tecla está pressionada, transcreve e cola ao soltar.
- **Toque rápido**: aperte e solte rápido (menos de ~0,35s) para travar a gravação ligada — toque de novo pra parar e transcrever.

Uma bolinha flutuante fica **sempre visível** na tela (por padrão no canto inferior direito) — arraste pra qualquer lugar, inclusive entre monitores, que a posição fica salva. Ela muda de acordo com o que tá acontecendo:

- **Parada**: mostra a logo (cachorro) discreta. Passar o mouse dá uma leve expandida; clicar (sem arrastar) abre o painel de configurações.
- **Gravando**: vira uma pilula com um mini equalizador ao vivo (faixas de frequência de verdade, via FFT — não é só volume geral).
- **Processando**: o anel ao redor do cachorro vira um spinner de carregamento até a transcrição terminar.

Botão direito na bolinha abre o mesmo menu de Configurações/Sair da bandeja.

Um ícone também fica na bandeja do sistema (perto do relógio, pode estar escondido nos "ícones ocultos" na primeira vez) — clique nele (ou clique direito → Configurações) pra abrir o painel. O app não aparece na barra de tarefas, só na bandeja.

## Painel de configurações

Clique na bolinha flutuante (ou botão direito no ícone da bandeja → **Configurações**). Painel com abas — dá pra mudar tudo sem editar arquivo nenhum na mão, e aplica na hora (sem precisar reiniciar):

- **Aba Configurações**: hotkey (clique no campo e aperte a tecla que quiser — aceita qualquer tecla, não só uma lista fixa) e microfone (lista os dispositivos de entrada disponíveis, ou deixa no padrão do sistema)
- **Aba Conta**: email/senha do ChatGPT, qual navegador usar no login automático (Automático/Chrome/Edge), botão "Testar login agora" pra forçar uma renovação e confirmar que está tudo certo, e um resumo de como o login automático funciona

Por baixo dos panos ainda é tudo salvo no `.env` — o painel só evita precisar editar na mão.

Os sons dizem o que aconteceu:

- **`start-stop-recording.mp3`** — toca ao começar e ao parar de gravar.
- **`done-transcribe.mp3`** — transcreveu e colou o texto.
- **Beep grave (400Hz)** — gravou, mas não veio fala reconhecível (microfone mudo ou baixo demais). Não é problema de sessão, então não abre navegador.
- **Dois beeps de 500Hz** — erro. O motivo fica em `quase_nada_voz.log`, na pasta do projeto.

O navegador so abre quando a API responde 401/403 de verdade — e mesmo assim ele tenta primeiro renovar a sessao pelo cookie salvo, sem abrir nada.

## Iniciar com o Windows

Já foi criado um atalho em `shell:startup` apontando para `start.bat` — o app sobe automaticamente no login. Para desativar, apague `QuaseNadaVoz.lnk` da pasta Startup (`Win+R` → `shell:startup`).

## Configurações (`.env`)

Editável direto ou pelo painel de configurações (recomendado):

- `OPENAI_EMAIL` / `OPENAI_PASSWORD` — obrigatórios, login da sua conta ChatGPT (login direto por senha, não Google/Microsoft).
- `OAI_DEVICE_ID` — opcional, tem um valor padrão.
- `HOTKEY` — código virtual da tecla (padrão `120` = F9). O painel de configurações escreve esse valor sozinho quando você captura uma tecla nova.
- `AUDIO_DEVICE` — nome do microfone escolhido no painel; vazio = padrão do sistema.
- `BROWSER_CHANNEL` — navegador usado no login automático: vazio (automático, tenta Chrome e depois Edge), `chrome` ou `msedge`.

## Distribuir para outras pessoas (`.exe`)

Pra alguém usar sem instalar Python, gere um executável único com [PyInstaller](https://pyinstaller.org/):

```
venv\Scripts\pyinstaller.exe --name "QuaseNadaVoz" --onefile --windowed --icon assets/icon.ico --add-data "assets;assets" app.py
```

Gera `dist/QuaseNadaVoz.exe` — é só mandar esse arquivo. Cada pessoa que abrir precisa configurar o próprio email/senha do ChatGPT no painel (ícone da bandeja → Configurações). Dados de cada instalação (`.env`, sessão, log) ficam em `%LOCALAPPDATA%\QuaseNadaVoz`, sem depender da pasta onde o `.exe` está.

Requer Google Chrome ou Microsoft Edge instalado (esse último já vem de fábrica em qualquer Windows) — o login automático abre um dos dois.

### Atualização automática

Rodando como `.exe`, o app confere sozinho (alguns segundos depois de abrir) se existe uma versão mais nova publicada nas [Releases do GitHub](https://github.com/ViniciusMateos/quase-nada-voz/releases). Se tiver, pergunta antes de baixar — aceitando, ele baixa, substitui o `.exe` atual e reabre sozinho.

Pra publicar uma atualização pra quem já tem o app instalado:
1. Bump em `version.py` (`APP_VERSION`).
2. Gere o novo `.exe` (comando acima).
3. Publique uma Release no GitHub com tag `vX.Y.Z` (maior que a anterior) e o `.exe` como anexo — quem já tem o app aberto recebe o aviso de atualização sozinho.

## Observações

- Usa o endpoint interno `chatgpt.com/backend-api/transcribe` (não oficial/documentado) — pode mudar ou parar de funcionar sem aviso.
- Interface feita com PySide6 (Qt oficial pra Python, licença LGPL — de graça mesmo em uso comercial/fechado), tema escuro customizado (`theme.py`).
- O ícone (`assets/icon.ico`) é a logo em `assets/logo.png`, colocada sobre um fundo turquesa (`#14B8A6`) com cantos arredondados. A bolinha flutuante usa `assets/dog.png` (só o cachorro, sem o círculo) pra ficar nítida em qualquer tamanho.
- Cada gravação fica registrada em `quase_nada_voz.log` (duração, pico do áudio, erro) — útil porque o app roda sem console.
- O microfone padrão do Windows é usado para gravação; troque o dispositivo padrão do sistema, ou escolha outro direto no painel de configurações.
