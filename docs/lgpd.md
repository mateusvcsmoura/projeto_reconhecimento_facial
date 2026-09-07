# Tratamento de dados pessoais e biométricos

Documento de conformidade do projeto. Descreve **o que** o sistema coleta,
**por quê**, **por quanto tempo** e **como** o titular pode sair.

Referência: Lei 13.709/2018 (LGPD). Dado biométrico é **dado pessoal
sensível** (art. 5º, II), e seu tratamento exige consentimento específico e
destacado do titular (art. 11, I).

---

## 1. Que dados são tratados

| Dado | Onde vive | Por quê |
|---|---|---|
| Nome | `alunos.nome` | Identificar o aluno na tela para o operador confirmar a presença |
| Matrícula | `alunos.matricula` | Chave de negócio, vinda da instituição |
| Recorte do rosto | Arquivo em `STORAGE_DIR` | Referência para recalcular o embedding se o modelo mudar |
| Embedding facial | `alunos.embedding` (`BYTEA`) | Comparação 1:N no reconhecimento |
| Modelo e dimensão do embedding | `alunos.embedding_modelo`, `embedding_dim` | Impedir comparação entre vetores incompatíveis |
| Data do consentimento | `alunos.consentimento_em` | Demonstrar a base legal do tratamento |
| Registros de presença | `presencas` | Finalidade do sistema |

**Não é coletado:** áudio, localização, contatos, documentos, nem qualquer
dado não listado acima. O frame completo da câmera **não** é armazenado —
apenas o rosto recortado e alinhado.

## 2. Finalidade

Controle de presença de alunos. Nada além disso. Os dados não são usados
para avaliação de desempenho, vigilância de comportamento, nem
compartilhados com terceiros.

## 3. Consentimento

O cadastro **não ocorre** sem consentimento explícito. O fluxo é:

1. o operador informa nome e matrícula;
2. o sistema exibe o termo — o que será coletado, para quê, e como pedir
   exclusão;
3. o titular responde;
4. **só então** a câmera é acionada.

A ordem importa: coletar a biometria para só depois perguntar inverteria o
que a lei exige. O momento do "sim" é gravado em `alunos.consentimento_em`.

Em código: `CadastrarAluno.executar` recebe `consentiu: bool` **sem valor
padrão**, de propósito — cadastrar sem consentimento não pode ser o caminho
mais fácil de escrever. Sem ele, o caso de uso levanta
`ConsentimentoNaoRegistrado` antes de qualquer outra validação.

## 4. Retenção

`RETENCAO_PRESENCAS_DIAS` define por quantos dias os registros de presença
são guardados. Padrão: 1825 dias (5 anos), prazo típico de guarda de
registro acadêmico. `0` desliga o expurgo.

```bash
python -m scripts.expurgar_presencas            # simula, não remove nada
python -m scripts.expurgar_presencas --apply    # efetiva
```

Feito para rodar agendado. Não requer câmera nem DeepFace.

A retenção vale para o **histórico de presença**, não para o cadastro: o
expurgo nunca apaga o aluno.

## 5. Direito à eliminação (art. 18, VI)

Opção **3** do menu, ou programaticamente via `ExcluirAluno`.

A exclusão remove, nesta ordem:

1. a linha em `alunos` — que carrega o embedding;
2. todas as presenças, por `ON DELETE CASCADE` (garantia do banco, não de
   uma varredura da aplicação);
3. o arquivo de imagem em `STORAGE_DIR`.

O banco vem primeiro: se a transação falhar, nada foi perdido. Se a remoção
do arquivo falhar depois, o erro é registrado para limpeza manual — mas o
dado já não está ligado a uma pessoa identificável dentro do sistema.

## 6. Segurança

| Controle | Como |
|---|---|
| **Anti-spoofing** | Ligado por padrão (`FACE_ANTI_SPOOFING`). Frames classificados como apresentação (foto impressa, tela) são recusados nos **dois** caminhos — cadastro e reconhecimento |
| **Menor privilégio no banco** | O usuário da aplicação faz apenas DML. DDL é exclusivo do usuário dono, usado só pelas migrations. Ver `scripts/sql/criar_usuario_aplicacao.sql` |
| **Segredos** | `DATABASE_URL` só via `.env`, que nunca é versionado. A aplicação falha no boot se a variável estiver ausente |
| **Logs** | Identificam o aluno pelo **id interno**, nunca por nome. Nunca registram imagem, embedding, nome de arquivo ou credencial. Coberto por teste |
| **Versionamento** | `.gitignore` bloqueia `*.db`, `/fotos/`, `/storage/`, `*.npy` e `.env` |
| **Portabilidade do banco** | O caminho da imagem é relativo; um dump não carrega caminhos de outra máquina |

## 7. Incidente registrado

O commit inicial do repositório versionou um banco SQLite com o nome real de
uma pessoa e 39 registros de presença. Nenhuma imagem facial e nenhum
embedding foram versionados.

O arquivo foi removido de **todo** o histórico do Git em 2026-09-07. Decisão,
verificação e risco residual em
[`adr/ADR-003-limpeza-do-historico.md`](adr/ADR-003-limpeza-do-historico.md).

## 8. Limites conhecidos

Declarados por honestidade, não resolvidos:

- **Sem criptografia em repouso.** Embeddings e imagens dependem do controle
  de acesso do PostgreSQL e do sistema de arquivos. Para uso real, o disco
  deveria ser cifrado.
- **Sem autenticação de operador.** Qualquer pessoa com acesso ao terminal
  pode cadastrar, reconhecer e excluir. O sistema é monousuário e local.
- **Sem trilha de auditoria.** Não há registro de *quem* excluiu um aluno.
- **O anti-spoofing produz falso positivo.** Verificado em 2026-09-07, em
  webcam comum com janela iluminada ao fundo: o modelo MiniFASNet recusou
  uma pessoa **ao vivo** três vezes seguidas, com 86% a 96% de confiança de
  que era uma apresentação. A verificação funciona — o modelo é que erra
  nessas condições. Mitigações no README (iluminação, resolução); em último
  caso, `FACE_ANTI_SPOOFING=false`, ao custo de perder a proteção do A7.
- **A eficácia contra ataques reais não foi medida.** Saber que o modelo
  recusa pessoas de verdade não diz quanto ele acerta contra foto impressa.
  Medir isso exige um protocolo próprio, com pares genuínos e de ataque.
- **Limiar não calibrado.** `FACE_THRESHOLD` é herança da biblioteca. A
  Fase 7 o calibra com FAR/FRR sobre dados reais.
