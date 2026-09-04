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
venv\Scripts\pyinstaller.exe --name "QuaseNadaVoz" --onefile --windowed --icon assets/icon.ico --add-data "assets;assets" app.py
```

Gera `dist/QuaseNadaVoz.exe` (não vai pro git — `dist/` está no `.gitignore`; distribuição é anexando o arquivo numa Release do GitHub, não commitando ele).

## Publicar uma atualização

Pra quem já tem o app instalado receber o aviso de atualização sozinho:

1. Bump em `version.py` (`APP_VERSION`).
2. Gere o novo `.exe` (comando acima).
3. Publique uma Release no GitHub com tag `vX.Y.Z` (maior que a anterior) e o `.exe` como anexo (asset).

O app confere sozinho (alguns segundos depois de abrir, só rodando como `.exe`) se existe uma versão mais nova nas Releases do GitHub. Se tiver, mostra um aviso; aceitando, baixa, substitui o `.exe` atual e reabre sozinho.

## Histórico de transcrições

`history.py` guarda as últimas `MAX_ITEMS` (5) transcrições em `history.json` (no mesmo diretório de dados do `.env`/log). A gravação acontece em `transcriber.py` **antes** da colagem, de propósito: se a colagem cair na janela errada ou falhar, o texto ainda dá pra recuperar pela aba Histórico do painel. Cada entrada nova empurra a mais antiga pra fora, então o arquivo não cresce. Erro de leitura/escrita nunca propaga — histórico quebrado vira lista vazia, pra não atrapalhar a transcrição em si.

## "Iniciar com o Windows"

O checkbox no painel escreve/remove um valor em `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` (`autostart.py`) — não precisa de admin, não usa atalho na pasta Startup.

## Observações técnicas

- Usa o endpoint interno `chatgpt.com/backend-api/transcribe` (não oficial/documentado) — pode mudar ou parar de funcionar sem aviso.
- Interface feita com PySide6 (Qt oficial pra Python, licença LGPL — de graça mesmo em uso comercial/fechado), tema escuro customizado (`theme.py`).
- O ícone (`assets/icon.ico`) é a logo em `assets/logo.png`, colocada sobre um fundo turquesa (`#14B8A6`) com cantos arredondados. A bolinha flutuante usa `assets/dog.png` (só o cachorro, sem o círculo) pra ficar nítida em qualquer tamanho.
- Cada gravação fica registrada em `quase_nada_voz.log` (duração, pico do áudio, erro) — útil porque o app roda sem console.
- O microfone padrão do Windows é usado para gravação; troque o dispositivo padrão do sistema, ou escolha outro direto no painel de configurações.
