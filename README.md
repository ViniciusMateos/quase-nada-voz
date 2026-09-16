# Quase Nada Voz

Ditado por voz: aperte uma tecla, fale, solte — o texto é transcrito e colado automaticamente onde estiver o cursor.

## Como usar

1. Baixe o `QuaseNadaVoz.exe` na [última versão](https://github.com/ViniciusMateos/quase-nada-voz/releases/latest) (em "Assets").
2. Dê duplo clique. Não precisa instalar nada — só ter o Google Chrome ou o Microsoft Edge (que já vem com o Windows).
3. Clique na bolinha que aparece na tela (ou no ícone perto do relógio — pode estar escondido nos "ícones ocultos" na primeira vez) e coloque seu email/senha do ChatGPT nas Configurações.
4. Pronto — segure **F9** pra ditar (dá pra trocar a tecla no painel).

**Se o Windows mostrar uma tela azul "O Windows protegeu o computador":** é normal pra qualquer `.exe` pequeno sem certificado pago de assinatura de código (não é vírus) — clique em **"Mais informações"** e depois em **"Executar assim mesmo"**.

**Como funciona:** segure a tecla, fale, solte — transcreve e cola sozinho onde o cursor estiver. Toque rápido (sem segurar) trava a gravação ligada até você tocar de novo.

No painel de Configurações (clique na bolinha ou no ícone da bandeja) dá pra trocar a tecla, o microfone, o navegador usado no login, e ligar o app junto com o Windows — tudo sem editar arquivo nenhum.

**Aba Histórico:** guarda as últimas 5 transcrições. Serve pra quando a colagem automática não cai onde devia (acesso remoto, janela que perdeu o foco) — clique numa transcrição pra ver o texto completo, ou use o botão "Copiar" e cole você mesmo. Só as 5 últimas ficam salvas; as mais antigas somem sozinhas.

**Sem campo de texto em foco:** se na hora de colar o app percebe que não tem onde colar (área de trabalho, lista de arquivos, janela de acesso remoto), ele não cola e mostra um balãozinho do lado da bolinha com o texto e dois botões: **Copiar** e **Ver no histórico**. Na dúvida, ele cola normalmente.

**Bolinha vermelha:** quer dizer que a conta não está funcionando (login não feito, sessão vencida, sem internet). Nesse estado o app nem tenta ditar — passe o mouse pra ver o motivo e clique pra resolver nas Configurações, aba Conta (o botão "Verificar agora" reconfere na hora).

Na primeira vez que você abre o painel ele te leva por um passo a passo rápido explicando cada parte. Dá pra rever quando quiser na aba **Tutorial**.

O app se atualiza sozinho: quando sair versão nova, ele avisa e atualiza com um clique — sai do ar por alguns segundos e volta contando de qual versão pra qual foi.

**Sobre a senha:** fica salva localmente sem criptografia (é o jeito mais simples de automatizar o login) — qualquer processo com acesso ao seu usuário Windows consegue ler. E como isso usa os endpoints internos do site da OpenAI (não é API oficial), pode violar os termos de uso deles e pode quebrar se a OpenAI mudar o login.

---

Quer mexer no código? Veja [DEVELOPMENT.md](DEVELOPMENT.md).
