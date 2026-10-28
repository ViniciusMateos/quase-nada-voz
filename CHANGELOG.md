# Changelog

## [1.3.0] — 2026-10-28

### Adicionado
- feat: o app virou programa de verdade no Windows — aparece em "Aplicativos instalados" com nome, ícone e versão, ganha atalho no Menu Iniciar e desinstala por lá, pelo botão em **Configurações > Desinstalar o app** (que deixa você escolher se apaga ou preserva login, histórico e configurações) ou por `--uninstall --quiet`. Instalação por usuário, sem admin e sem instalador separado; quem recusar a oferta na primeira vez tem um botão "Instalar neste computador" no painel. Instalar também repõe o "iniciar com o Windows" apontando pro app instalado, em vez de seguir abrindo a cópia solta de onde a opção foi ligada

### Corrigido
- fix: a bolinha — e o avisinho preso nela — desapareciam no `Win+D` e no "minimizar tudo", que mandam minimizar em toda janela aberta. Era isso que fazia o app parecer que morria sozinho do nada: agora ela ignora os dois, e volta sem roubar o foco de onde você está digitando

## [1.2.0] — 2026-09-16

### Adicionado
- feat: o app trava o ditado quando a conta não está funcionando — a bolinha fica vermelha, o motivo aparece ao passar o mouse e clicar leva pro login, em vez de gravar e abrir um navegador do nada no meio do trabalho
- feat: aba Conta mostra o status da sessão, com botão "Verificar agora"
- feat: quando não tem campo de texto em foco (área de trabalho, janela de acesso remoto), o texto não é colado às cegas — aparece um balãozinho ao lado da bolinha com Copiar e "Ver no histórico". Na dúvida, cola normalmente
- feat: passo a passo guiado na primeira abertura do painel, e aba Tutorial pra rever quando quiser
- feat: olho na senha, com a senha "descriptografando" ao mostrar e voltando pra bolinha ao esconder
- feat: build de dev separado (`python build.py --dev`), que roda ao mesmo tempo que o app normal com ícone, dados e atalhos próprios

### Corrigido
- fix: atualizar fechava o app e não abria a versão nova — o `.exe` novo herdava o ambiente do antigo e morria tentando rodar de uma pasta temporária que já não existia. Agora ele sobe limpo e, ao voltar, avisa na tela de qual versão pra qual foi
- fix: dá pra escolher a própria tecla atual como atalho — antes apertar F9 pra confirmar F9 começava a gravar em vez de ser capturado

### Modificado
- update: o painel não tem mais botão Salvar: cada mudança grava na hora
- update: log de áudio traz o rms junto do pico, e o build de dev guarda a última gravação em wav pra diagnóstico

### Documentação
- docs: README explica a bolinha vermelha e o tutorial; DEVELOPMENT documenta o canal dev/prod, a troca do `.exe` em execução e a trava de sessão

## [1.1.1] — 2026-09-04

### Adicionado
- feat: histórico atualiza sozinho com o painel aberto (antes só aparecia transcrição nova fechando e abrindo de novo) e ganhou botão "Atualizar"

## [1.1.0] — 2026-09-04

### Adicionado
- feat: aba "Histórico" no painel com as últimas 5 transcrições — clique pra ver o texto completo, botão "Copiar" pra jogar no clipboard sem precisar expandir. Salva antes de colar, então serve pra recuperar o texto quando a colagem automática cai na janela errada (acesso remoto) ou falha

## [1.0.3] — 2026-09-03

### Corrigido
- fix: bolha flutuante reafirma o "sempre no topo" na hora (via evento de mudança de janela em primeiro plano), não só a cada 3s — o timer sozinho podia parar de disparar depois de muitas horas rodando

## [1.0.2] — 2026-09-02

### Adicionado
- feat: opção "Iniciar com o Windows" no painel de configurações (liga/desliga direto pelo registro, sem precisar mexer em atalho na pasta Startup)

### Documentação
- docs: README simplificado pra quem só usa o app (baixa e usa); setup de código-fonte, geração do .exe e publicação de updates viraram DEVELOPMENT.md

## [1.0.1] — 2026-09-02

### Adicionado
- feat: número da versão aparece no rodapé do painel de configurações
- feat: aviso de atualização ganha visual próprio (mesma cara do painel), com estado de "baixando" e erro inline, em vez de uma caixa de mensagem genérica do Windows

## [1.0.0] — 2026-09-02

Primeira versão distribuível do app: dá pra compartilhar um `.exe` único com qualquer pessoa (sem precisar instalar Python), e o próprio app se atualiza sozinho a partir daqui.

### Adicionado
- feat: menu de contexto (botão direito) na bolha flutuante, com as mesmas opções da bandeja
- feat: proteção contra abrir duas instâncias do app ao mesmo tempo
- feat: app se atualiza sozinho — confere a última versão publicada nas Releases do GitHub, baixa e reabre
- feat: painel de configurações ganha inputs, combos e abas animados
- feat: escolha do navegador usado no login automático (Automático/Chrome/Edge)

### Modificado
- refactor: resolução de paths centralizada, preparando o app pra rodar empacotado como `.exe`
- update: login automático agora tenta o Microsoft Edge se não achar o Chrome instalado
- update: configurações não aparece mais como item separado na barra de tarefas (só na bandeja)
- update: bolha flutuante reafirma sozinha o "sempre no topo", que o Windows as vezes derrubava

### Documentação
- docs: README documenta o menu de contexto, como gerar o `.exe` e como funciona o auto-update
