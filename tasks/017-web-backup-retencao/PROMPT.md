# Prompt de execução — 017 / Luna 6 High

Você é **Luna 6, esforço High**, executor no repositório
`projeto_reconhecimento_facial`.

**Execute somente a task 017 — Backup cifrado, retenção e restauração. O desenho e o plano estão
definidos. Apenas execute o escopo autorizado, teste e documente; não reabra
brainstorming, não delegue e não avance automaticamente para outra task.**

## Leitura obrigatória

1. `AGENTS.md`, `CLAUDE.md`, instruções relevantes e arquitetura atual.
2. `docs/PLANEJAMENTO-FUTURO-PRESENCA-WEB.md`.
3. `docs/FACEDIFF-WEB-ARQUITETURA-OPERACAO.md`.
4. `tasks/WEB-CONTRATO-EXECUCAO.md` e `tasks/WEB-MIGRACOES.md`.
5. `tasks/017-web-backup-retencao/DESENHO.md` e `tasks/017-web-backup-retencao/PLANO.md`, integralmente.
6. Resultados reais das dependências: **016**.

Use Superpowers executing-plans quando disponível; aprove internamente escolhas
rotineiras, sem pedir confirmações de decisões já definidas. Isso não amplia
permissões de banco, dados reais, contratação ou publicação.

## Entrega específica

Implementar ferramentas e testes locais, sem conexão ao Google Drive do usuário nem dados pessoais. Duas cópias planejadas: local cifrada e externa cifrada. Usar rclone crypt para cifrar antes de enviar, com segredos fora do repo/logs e custódia independente. O backend remoto em testes é filesystem temporário fake; não confundir teste local com restore externo realizado.

Backup diário e manual pré-apresentação: lock único, pausar escritas, aguardar jobs/transações, dump lógico compatível PostgreSQL+referências do mesmo ponto, manifesto/hashes/versão schema/app. Staging privado temporário, cifrar local, verificar cryptcheck, limpar staging e liberar manutenção em finally. Cópia externa transfere bytes já cifrados; marcar completa só após verificação/download de amostra. Credenciais nunca no pacote.

Retenção recomendada: três gerações completas e logs3dias, limitada pela data final autorizada da demonstração~10dias. Data final prevalece mesmo se convite7dias ainda válido. Pendentes expiram em min(submissão+7dias,data_final), imagens de verificação só temporárias; rotinas de limpeza idempotentes com dry-run padrão e apply explícito. Não inferir que apagar FK anonimiza fotos.

Planejar OAuth próprio drive.file em conta/pasta dedicada; root_folder_id não limita privilégios OAuth. Nada de login agora. Simular token expirado, quota, upload interrompido, arquivo corrompido. Não contratar backup adicional Hostinger.

Restore em base descartável identificada, reaplicar exclusões posteriores ao backup e invalidar tokens/sessões restaurados. Relatório só contém evidência técnica sem dados. Documentar encerramento incluindo lixeira/revisões/cópias do provedor e cobrança; não executar encerramento real nesta task.

### Contratos que você deve respeitar

GerarBackup.executar(destino_local,agora,modo) -> ManifestoBackup.
TransportarBackup.executar(geracao,destino_adapter) -> ResultadoVerificado.
RestaurarEnsaio.executar(geracao,banco_descartavel,autorizacao) -> EvidenciaRestore.
ExpurgarWeb.planejar(agora) -> PlanoExpurgo; aplicar exige confirmação explícita do ambiente/alvos.
Scripts sem parâmetros de segredo; adaptadores de subprocesso evitam exposição e shell interpolation.

### Provas mínimas

- Dump/fotos consistentes; erro libera manutenção e remove plaintext temporário.
- Upload falho não marca geração completa nem apaga última íntegra; hash divergente falha.
- Restore sem chave falha explicitamente; restore reaplica exclusões e revoga tokens.
- Prazo final interrompe coleta/retencão; dry-run não remove arquivo; escopo de exclusão não escapa do diretório.

## Limites e conclusão

**Não criar interface, páginas, templates ou fluxo de câmera no navegador.** Use testes/cliente HTTP para provar a funcionalidade. UI fica exclusivamente na020.

Não executar migration, acessar banco operacional, conectar Google Drive,
provisionar VPS, realizar deploy ou usar rostos reais sem autorização específica
vigente. Preparar código/migration/testes não significa autorização para aplicá-los.
Não desabilitar antispoofing ou alterar threshold0,30 para fazer testes passarem.
Não interpretar matrícula informada como autenticação.

Ferramentas de backup/retencão e restore sintético local testadas ou dependência de banco explicitamente pendente. Drive real não conectado e restore remoto não alegado.

Ao terminar, criar `tasks/017-web-backup-retencao/RESULTADO.md`, atualizar índice e relatar comandos
efetivos, contratos, pendências e estado dos gates. **Não fazer commit/push por
autorização herdada de tasks001–008.** A restrição da consolidação atual prevalece;
se o usuário autorizar explicitamente publicação nesta execução, fazer commit
em PT-BR e push na main conforme procedimento do contrato comum. Não contratar
ou implantar como consequência do push.

## Regra obrigatória de commit e push

Antes de qualquer commit ou push, leia ou releia o arquivo AGENTS.md na raiz do repositório e siga suas instruções vigentes. A autorização desta tarefa pode limitar ou proibir a publicação; esta regra não amplia autorizações.

- Mensagens de commit sempre em PT-BR. Não se identifique como Co Author nem adicione Co-authored-by; use somente a identidade e as credenciais Git já configuradas do solicitante, sem reconfigurar autoria.
- Se a entrega envolver muitos arquivos ou unidades lógicas distintas, divida-a em commits separados e organizados por escopo; não agrupe mudanças independentes em um commit monolítico.
- Adicione ao staging apenas caminhos explícitos e revise git diff --cached --stat, git diff --cached --check e o conteúdo staged antes de cada commit. Faça push somente para o branch/remoto autorizado e sem force.
