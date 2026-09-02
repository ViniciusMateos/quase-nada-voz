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

O app se atualiza sozinho: quando sair versão nova, ele avisa e atualiza com um clique.

**Sobre a senha:** fica salva localmente sem criptografia (é o jeito mais simples de automatizar o login) — qualquer processo com acesso ao seu usuário Windows consegue ler. E como isso usa os endpoints internos do site da OpenAI (não é API oficial), pode violar os termos de uso deles e pode quebrar se a OpenAI mudar o login.

---

Quer mexer no código? Veja [DEVELOPMENT.md](DEVELOPMENT.md).
