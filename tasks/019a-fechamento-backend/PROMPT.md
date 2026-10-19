# Prompt — Luna 6 High — Task 019A

- Execute somente a task `tasks/019a-fechamento-backend`, inline e sem delegação.
- Leia integralmente AGENTS.md, CLAUDE.md, contrato comum, WEB-MIGRACOES.md, DESENHO.md e PLANO.md desta task, resultados 017–019 e código relevante.
- O backend tem implementação e provas sintéticas, mas a 019 não aprovou o gate da interface. Feche as pendências; não implemente a 020.
- Siga os checkboxes do plano: ambiente, roundtrip cifrado real, runtime Compose/Linux, proteção do cadastro público, fluxo até painel/CSV, regressão e atualização documental.
- Preserve arquitetura e contratos. Para cada bug, reproduza com teste, faça a menor correção e reexecute a prova.
- Use exclusivamente dados sintéticos, bancos e volumes descartáveis autorizados. Não acesse escola, Drive, VPS ou dados biométricos reais; não execute deploy nem altere threshold/anti-spoofing.
- Não contorne falta de permissão. Falha de ambiente deve aparecer como bloqueio concreto; mocks, skips e configuração estática não substituem restore/runtime reais.
- Registre o resultado de cada critério em RESULTADO.md e emita separadamente os gates de backend e operação real. Não declare capacidade da VPS com benchmark fake.
- Ao concluir implementação autorizada, releia AGENTS, revise o staging, faça commits em PT-BR separados por escopo e push para main usando a identidade existente, sem Co-authored-by ou force push.
- Entregue resumo em bullets: correções, comandos/resultados, limitações, gates e commits. Não avance automaticamente para interface.
