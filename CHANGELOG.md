# Changelog

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
