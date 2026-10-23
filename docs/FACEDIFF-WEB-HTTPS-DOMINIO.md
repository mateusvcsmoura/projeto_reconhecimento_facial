# FaceDiff web — HTTPS e domínio para a VPS

**Estado: decisão pendente (23/10/2026).** Este documento reúne as opções para
publicar o FaceDiff com HTTPS na Hostinger KVM 2. Nenhum domínio foi contratado
e nada foi configurado na VPS. Preços e ofertas citados precisam ser conferidos
no momento da contratação.

## Por que o HTTPS é obrigatório

O navegador só libera a câmera (`getUserMedia`) em páginas seguras. No
desenvolvimento local funciona porque `127.0.0.1`/`localhost` contam como
seguros. Na VPS, acessando por `http://IP`, os celulares **bloqueiam a câmera**,
e o cadastro facial e a verificação de presença deixam de funcionar.

## Como funciona

1. Escolhe-se um nome, por exemplo `presenca.seudominio.com.br`.
2. No painel de DNS do domínio, cria-se um registro **A** apontando esse nome
   para o **IP da VPS** (e um **AAAA**, se a VPS tiver IPv6).
3. O Caddy, já incluído em [`deploy/web/compose.yaml`](../deploy/web/compose.yaml)
   e [`deploy/web/Caddyfile`](../deploy/web/Caddyfile), recebe o primeiro
   acesso, prova ao Let's Encrypt que controla o domínio e obtém o certificado
   em segundos. A renovação é automática e o certificado é **gratuito**.
4. No `.env` do deploy bastam duas variáveis:

   ```env
   WEB_DOMAIN=presenca.seudominio.com.br
   CADDY_ACME_EMAIL=responsavel@exemplo.com
   ```

   O compose deriva o restante delas, inclusive `WEB_PUBLIC_ORIGIN`, usada na
   validação de origem e CSRF.

## Opções para o domínio

| Opção | Custo estimado | Observações |
|---|---|---|
| Domínio grátis da oferta Hostinger | R$ 0 no primeiro ano | O carrinho de 17/10/2026 anunciava domínio grátis por um ano. Confirmar se vale para o plano e o prazo contratados. Se valer, é o caminho mais simples |
| Domínio `.com.br` no [Registro.br](https://registro.br) | cerca de R$ 40/ano | Mais profissional e sob controle do grupo. Conferir o preço atual |
| Subdomínio grátis do [DuckDNS](https://www.duckdns.org) (`nome.duckdns.org`) | R$ 0 | Funciona com o Caddy e atende uma apresentação acadêmica. Depende de um serviço gratuito de terceiros |

### Alternativas não recomendadas

- **Acesso pelo IP sem domínio:** sem HTTPS, os celulares bloqueiam a câmera.
- **Certificado autoassinado:** mostra alerta de segurança em todos os celulares
  e pode impedir o acesso à câmera.
- **Túneis com endereço aleatório** (por exemplo, túneis rápidos sem conta): a URL
  muda a cada reinício e precisa coincidir com `WEB_PUBLIC_ORIGIN`, o que quebra
  links já enviados e a validação de origem.

## Cuidados práticos

- **Configurar o DNS 1 a 2 dias antes da apresentação.** A propagação costuma
  levar minutos, mas pode demorar horas.
- **Abrir as portas 80 e 443** no firewall da VPS e no painel da Hostinger, se
  houver. O Caddy usa a porta 80 para validar o domínio e redirecionar para HTTPS.
- **Não recriar os dados do Caddy sem necessidade.** O Let's Encrypt limita
  tentativas repetidas; o compose mantém o certificado em volume persistente.
- **Testar no celular** pelo 5G e pelo Wi-Fi antes do dia, junto com o ensaio de
  carga previsto em [arquitetura e operação](FACEDIFF-WEB-ARQUITETURA-OPERACAO.md).

## Próximo passo

Escolher uma das opções acima. Com a decisão, prepara-se o `.env` de deploy e o
passo a passo de instalação na VPS (Ubuntu 24.04 LTS, Docker/Compose, Caddy e
HTTPS), seguindo o checklist da seção 6 de
[arquitetura e operação](FACEDIFF-WEB-ARQUITETURA-OPERACAO.md).
