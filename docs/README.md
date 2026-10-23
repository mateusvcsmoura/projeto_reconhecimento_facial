# Documentação do projeto

## Estado e próximos passos

- [Estado atual e evidências](ESTADO-ATUAL-E-EVIDENCIAS.md)
- [Planejamento futuro de presença pela web](PLANEJAMENTO-FUTURO-PRESENCA-WEB.md)
- [FaceDiff web: arquitetura e operação na Hostinger KVM 2](FACEDIFF-WEB-ARQUITETURA-OPERACAO.md)
- [FaceDiff web: roadmap e plano de validação](FACEDIFF-WEB-ROADMAP.md)
- [FaceDiff web: contas, sessões e autorização](FACEDIFF-WEB-AUTH.md)
- [FaceDiff web: runtime e compatibilidade Linux](FACEDIFF-WEB-RUNTIME.md)
- [FaceDiff web: HTTPS e domínio para a VPS](FACEDIFF-WEB-HTTPS-DOMINIO.md)
- [Tarefas: desenhos, planos, prompts e resultados](../tasks/README.md)

## Arquitetura e privacidade

- [Arquitetura atual](../ARCHITECTURE.md)
- [Baseline da arquitetura](baseline-arquitetura.md)
- [Decisões de arquitetura](adr/)
- [LGPD e tratamento de dados](lgpd.md)

## Funcionalidades atuais

- [Turmas](TURMAS.md)
- [Captura automática](CAPTURA-AUTOMATICA.md)
- [Landmarks faciais](FACIAL-LANDMARKS.md)

## Material acadêmico e evidências

- [Consolidação acadêmica](ML-CONSOLIDACAO-ACADEMICA.md)
- [Matriz de rastreabilidade](ML-MATRIZ-RASTREABILIDADE.md)
- [Comparação de abordagens](ML-COMPARACAO-ABORDAGENS.md)
- [Guia de reprodutibilidade](ML-GUIA-REPRODUTIBILIDADE.md)
- [Preparação experimental](ML-EXPERIMENT-SETUP.md)
- [Roteiro de apresentação](ML-ROTEIRO-APRESENTACAO.md)
- [Demonstração](apresentacao.md)
- [Perguntas para avaliação](ML-PERGUNTAS-BANCA.md)

Os relatórios `ML-ETAPA-*-RESULTADO.md` e a auditoria histórica foram
preservados como fontes das evidências. Seus números descrevem as execuções
registradas, não resultados atuais ou comprovação de acurácia biométrica.

## Limpeza documental de 17/10/2026

Removidos os três planos locais de execução das etapas experimentais 3, 4 e 5
em `docs/superpowers/plans/`, já encerradas e documentadas nos relatórios.
Esses arquivos eram ignorados pelo Git, portanto sua remoção é local e não
aparece como exclusão no histórico versionado. Especificações de arquitetura,
ADRs, LGPD, evidências, guias operacionais e todos os pacotes de `tasks/`
foram preservados. O planejamento web foi consolidado em 17/10/2026; sua
runtime e autenticação foram implementados e publicados na `main`; a revisão
`0005` foi aplicada ao banco local `escola` e os testes PostgreSQL descartáveis
passaram. Não houve deploy.
Implantação e validação operacional continuam pendentes.
