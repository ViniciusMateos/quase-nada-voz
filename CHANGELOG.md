# Changelog

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
