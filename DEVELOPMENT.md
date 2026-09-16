# Desenvolvimento

Documentação técnica pra quem for mexer no código. Quem só quer usar o app não precisa de nada disso — veja o [README](README.md).

## Rodando do código-fonte

- `venv/` com as dependências de `requirements.txt` instaladas.
- `playwright install chromium` (fallback caso a máquina não tenha Chrome nem Edge).
- `.env` na raiz do projeto (variáveis descritas abaixo).

```
venv\Scripts\activate
python app.py
```

`start.bat` faz a mesma coisa mas com o terminal visível (útil pra ver logs/erros).

Rodando do código-fonte, `.env`, sessão salva e log ficam na própria pasta do projeto. Rodando o `.exe` empacotado, ficam em `%LOCALAPPDATA%\QuaseNadaVoz`, sem depender de onde o `.exe` está — isso é resolvido sozinho por `paths.py`.

## Configurações (`.env`)

Editável direto ou pelo painel de configurações (recomendado):

- `OPENAI_EMAIL` / `OPENAI_PASSWORD` — obrigatórios, login da conta ChatGPT (login direto por senha, não Google/Microsoft).
- `OAI_DEVICE_ID` — opcional, tem um valor padrão.
- `HOTKEY` — código virtual da tecla (padrão `120` = F9). O painel escreve esse valor sozinho quando você captura uma tecla nova.
- `AUDIO_DEVICE` — nome do microfone escolhido no painel; vazio = padrão do sistema.
- `BROWSER_CHANNEL` — navegador usado no login automático: vazio (automático, tenta Chrome e depois Edge), `chrome` ou `msedge`.

## Login automático — como funciona por baixo dos panos

1. `auth.py` abre uma janela do Chrome ou Edge (via Playwright), preenche o login sozinho e extrai a sessão.
2. A sessão fica salva localmente. Enquanto for válida, o token de acesso é renovado via requisição HTTP simples — sem abrir navegador.
3. Quando o token expira (~1h), renova sozinho a partir da sessão salva.
4. Quando a própria sessão expira de vez (semanas), refaz o login sozinho com o email/senha salvos.

Se aparecer captcha ou verificação extra que a automação não sabe resolver, a janela fica aberta por até 3 minutos esperando o login manual — o app segue sozinho a partir daí. Se travar, um screenshot é salvo em `login_debug.png`.

Detalhes pra reduzir bloqueio por automação: usa o navegador de verdade instalado (não um Chromium de teste), digita com delay simulando digitação humana.

Isso usa os endpoints internos do site da OpenAI (não é API oficial) — pode violar os termos de uso deles e pode quebrar quando a OpenAI mudar o layout do login.

## Gerar o `.exe`

```
python build.py         ->  dist/QuaseNadaVoz.exe     (o app de verdade)
python build.py --dev   ->  dist/QuaseNadaVozDev.exe  (build de testes)
```

Gera em `dist/` (não vai pro git — `dist/` está no `.gitignore`; distribuição é anexando o arquivo numa Release do GitHub, não commitando ele).

### Canal dev x prod

O Dev existe pra testar tudo antes de commitar e lançar, e roda **ao mesmo tempo** que o app normal sem se atrapalharem: nome, `APP_ID`, ícone (turquesa em vez de verde, com uma ferramenta no cachorro), pasta de dados, trava de instância única e chave de "iniciar com o Windows" são todos separados.

O canal vai gravado dentro do `.exe` num `channel.txt`, que `paths.py` lê na subida; rodando pelo código-fonte dá pra forçar com `QNV_CHANNEL=dev` (aí os dados ficam em `.dev-data/`, fora do git). O Dev também **nunca** olha as Releases do GitHub — baixaria o app normal por cima dele.

Um `.exe` já rodando não pode ser sobrescrito, mas pode ser renomeado: pra trocar o Dev sem fechar o que está aberto, gere em outra pasta, renomeie o atual pra `.old-<timestamp>` e mova o novo pro lugar.

## Publicar uma atualização

Pra quem já tem o app instalado receber o aviso de atualização sozinho:

1. Bump em `version.py` (`APP_VERSION`).
2. Gere o novo `.exe` (comando acima).
3. Publique uma Release no GitHub com tag `vX.Y.Z` (maior que a anterior) e o `.exe` como anexo (asset).

O app confere sozinho (alguns segundos depois de abrir, só rodando como `.exe`) se existe uma versão mais nova nas Releases do GitHub. Se tiver, mostra um aviso; aceitando, baixa, substitui o `.exe` atual e reabre sozinho.

### Como a troca do `.exe` acontece

Não dá pra sobrescrever um `.exe` em execução, mas dá pra **renomear**: o atual vira `.old-<timestamp>`, o baixado assume o nome original e é aberto com `--after-update=<versão antiga>`. A versão nova espera (até 30s) a antiga soltar a trava de instância única, apaga a sobra `.old` e avisa na tela de qual versão pra qual veio. Se qualquer passo falhar, desfaz tudo e o app continua como estava.

> O `.exe` novo **tem** que subir com o ambiente limpo: `PYINSTALLER_RESET_ENVIRONMENT=1` e sem nenhuma variável `_PYI_*` herdada. Herdando, ele se acha um subprocesso do app antigo e tenta rodar da pasta temporária dele — que é apagada quando o antigo fecha. Resultado: o app fechava e não voltava nada, sem erro no log. Esse era *o* bug da atualização.

Pra testar o fluxo inteiro sem publicar nada, o Dev tem "Testar atualização (dev)" na bandeja: ele copia o próprio `.exe` e escreve um `update_feed.json` na pasta de dados fingindo que saiu versão nova.

## Trava de sessão

`session.py` confere a conta ao subir e a cada 10 minutos, e `auth.check_session()` responde `ok` / `expired` / `no_credentials` / `offline` **sem nunca abrir navegador**. Enquanto não estiver `ok`, a bolinha fica vermelha e o ditado é recusado antes de gravar (`_start_recording` devolve `False`, e o `hotkey.py` respeita isso em vez de achar que começou a gravar).

Sem essa trava o caminho era: grava, manda pra API, toma 401, tenta relogar e **abre um navegador do nada** no meio do trabalho — que era o que acontecia com sessão vencida.

O e-mail associado à sessão fica em `session_meta.json` (fora do git). Trocar de conta no painel apaga o `.browser_profile` e os cookies; reabrir o painel com a mesma conta não apaga nada.

## Gravação: um stream de microfone por ditado

`recorder.py` abre um stream novo a cada gravação e fecha no fim. Antes o stream ficava aberto desde que o app subia — depois de dias rodando (suspensão do USB do headset, queda do acesso remoto) ele continuava entregando áudio com nível plausível, mas corrompido: a API recebia e devolvia vazio ou lixo, sem erro nenhum no log. Abrir leva ~80ms, menos do que alguém demora pra começar a falar.

`start()` é chamado de dentro do hook global de teclado, e o Windows remove o hook em silêncio se ele demorar pra responder — por isso a abertura do microfone roda numa thread à parte. Cada gravação tem um número de sessão, pra um stream que ainda está abrindo/fechando de uma gravação anterior não misturar áudio na atual.

> Pico 32767 no log (áudio batendo no teto) **não** é sinal de problema por si só: esse headset satura assim há semanas e transcreve normal. Pra separar "a API mudou" de "o áudio chegou estragado", mande uma fala sintética (TTS do Windows) direto pro endpoint.

## Histórico de transcrições

`history.py` guarda as últimas `MAX_ITEMS` (5) transcrições em `history.json` (no mesmo diretório de dados do `.env`/log). A gravação acontece em `transcriber.py` **antes** da colagem, de propósito: se a colagem cair na janela errada ou falhar, o texto ainda dá pra recuperar pela aba Histórico do painel. Cada entrada nova empurra a mais antiga pra fora, então o arquivo não cresce. Erro de leitura/escrita nunca propaga — histórico quebrado vira lista vazia, pra não atrapalhar a transcrição em si.

Assim que a transcrição entra no histórico, `transcriber.py` avisa o app (`on_saved`) e o painel aberto atualiza na hora. O timer de 1,5s do painel fica só como rede de segurança.

## Detecção de campo de texto em foco

Antes de colar, `focus.py` responde `yes`, `no` ou `unknown` — e **só `no` deixa de colar** (mostra o balão de `notice.py` com Copiar / Ver no histórico). Errar pro lado do `no` num campo de texto de verdade quebraria o uso principal, então na dúvida cola:

- `no`: nada em foco, área de trabalho/barra de tarefas, cliente de acesso remoto (mstsc, RustDesk, AnyDesk, TeamViewer...), ou UI Automation dizendo que o foco é um tipo claramente não-texto (lista, botão, aba, menu, árvore).
- `yes`: terminal, janela com caret do Win32, ou elemento UIA do tipo Edit/Document ou com TextPattern.
- `unknown`: todo o resto. De propósito: Pane/Window/Custom (apps Java como o PyCharm aparecem como um bloco só), células de planilha (Excel aceita colar).

Pegadinhas que custaram caro descobrir:
- **Chrome/Electron** (VS Code, WhatsApp, Discord) só montam a árvore de acessibilidade depois da primeira consulta — até lá devolvem um painel genérico **sem foco de teclado**. Por isso: elemento sem `HasKeyboardFocus` é `unknown`, e `focus.warm_up()` consulta uma vez quando a gravação começa, pra checagem do fim já vir certa.
- **"Tem valor editável" não é campo de texto**: item de arquivo no Explorer declara ValuePattern editável (é o renomear).
- **COM**: o `comtypes` inicializa o COM na thread do primeiro import. `sys.coinit_flags` só é definido ali, em thread de fundo — nunca na thread do Qt.

A UIA roda numa thread com timeout de 1,5s (app travado do outro lado não segura a transcrição). Funciona empacotado no `.exe` (testado).

## "Iniciar com o Windows"

O checkbox no painel escreve/remove um valor em `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` (`autostart.py`) — não precisa de admin, não usa atalho na pasta Startup.

## Observações técnicas

- Usa o endpoint interno `chatgpt.com/backend-api/transcribe` (não oficial/documentado) — pode mudar ou parar de funcionar sem aviso.
- Interface feita com PySide6 (Qt oficial pra Python, licença LGPL — de graça mesmo em uso comercial/fechado), tema escuro customizado (`theme.py`).
- O ícone (`assets/icon.ico`) é a logo em `assets/logo.png`, colocada sobre um fundo turquesa (`#14B8A6`) com cantos arredondados. A bolinha flutuante usa `assets/dog.png` (só o cachorro, sem o círculo) pra ficar nítida em qualquer tamanho.
- O painel não tem botão Salvar: cada campo grava sozinho ao mudar ou ao perder o foco (`settings_dialog.py`). Enquanto o campo do atalho espera uma tecla, o hook global fica `paused` — senão apertar a tecla que já estava valendo começava a gravar em vez de ser capturada — e só volta quando a tecla é solta.
- O passo a passo (`tour.py`) escurece o painel e recorta um buraco com o mesmo contorno arredondado do que está em foco; o recorte inclui a região do cartão, senão o próprio cartão sumia atrás do escurecido.
- Cada gravação fica registrada em `quase_nada_voz.log` (duração, pico do áudio, erro) — útil porque o app roda sem console.
- O microfone padrão do Windows é usado para gravação; troque o dispositivo padrão do sistema, ou escolha outro direto no painel de configurações.
