# FaceDiff web — roteiro de apresentação e contingência

Este roteiro acompanha a interface da tarefa 020. A implementação está parcial;
consulte o resultado 020 para
separar testes aprovados das validações ainda pendentes. Este documento não
autoriza deploy nem o uso de pessoas ou dados reais.

## Inspeção local atual

O servidor de revisão iniciado nesta execução está em
[http://127.0.0.1:8000](http://127.0.0.1:8000). Ele usa configuração de teste e
uma URL sintética de PostgreSQL sem serviço ativo. Landing, login e assets podem
ser inspecionados; as chamadas que exigem conta, sessão ou persistência falham
sem backend conectado. Não use dados biométricos nesse servidor.

Para uma execução local separada, configure as variáveis `WEB_*` conforme o
[guia de runtime](FACEDIFF-WEB-RUNTIME.md) e execute no PowerShell:

```powershell
.venv-ml\Scripts\python.exe -m uvicorn src.web_main:create_web_app --factory --host 127.0.0.1 --port 8000
```

`localhost` permite testar getUserMedia em alguns navegadores sem HTTPS. Acesso
por outros dispositivos exige HTTPS e infraestrutura configurada; não exponha a
porta local à rede como atalho.

## Ensaio antes de uma apresentação futura

1. Confirmar ambiente, navegador/dispositivo, build e versão de schema com o
   responsável técnico. Verificar saúde do serviço, fila e acesso antes de abrir
   links para participantes.
2. Fazer backup pelo procedimento de operação aprovado e confirmar a evidência
   de restauração definida para aquele ambiente. Não usar backup sintético como
   confirmação de cópia operacional.
3. Usar somente contas, turmas e participantes cuja autorização e finalidade
   estejam documentadas. Confirmar a identidade por processo independente; a
   matrícula digitada não autentica uma pessoa.
4. Abrir uma sessão de teste, conferir expiração/limites e enviar o link por um
   canal autorizado. Confirmar que o professor vê estados e metadados previstos,
   sem fotografias ou embeddings.
5. Testar câmera permitida/negada, dispositivo ocupado, rede interrompida,
   atualização da página, fila cheia e alternativa acessível. Confirmar presença
   apenas quando a API informar o estado final persistido.
6. No encerramento, revogar links temporários, fechar sessão e seguir o plano de
   retenção/eliminação autorizado. Não limpar banco ou arquivos em uma
   apresentação sem procedimento revisado.

## Contingências

- **Câmera negada ou indisponível:** interromper a captura, explicar como rever
  a permissão e oferecer a alternativa acessível aprovada. Não pedir que a pessoa
  envie imagem por canal informal.
- **Rede, fila ou API indisponível:** informar que o resultado ainda não foi
  confirmado; evitar reenvio repetido e consultar o estado da tentativa conforme
  o backend. Nunca mostrar presença confirmada por sucesso local da câmera.
- **Revisão necessária:** encaminhar ao professor pelo fluxo autenticado e
  registrar decisão/justificativa na API. Não permitir que a interface conceda
  presença diretamente.
- **Falha durante demonstração:** usar ambiente e registros sintéticos. Não
  contornar verificação, alterar limiar, desabilitar anti-spoofing ou simular
  aprovação biométrica.

## Evidência que ainda falta

O workspace desta revisão não teve browser disponível para CUA, então a matriz
responsiva, inspeção visual, teclado/leitor de tela e custos de animação ainda
precisam de validação manual. Não foram feitos ensaios Android/iOS/notebook,
deploy, piloto, avaliação biométrica ou coleta de rostos.
