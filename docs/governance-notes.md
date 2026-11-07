# Registro de Governança — Uma Voting

**Projeto**: Uma Voting
**Constituição atual**: 2.0.0
**Última atualização**: 2026-11-07

## 1. Histórico de versões

| Versão | Data | Tipo | Resumo |
|---|---|---|---|
| 1.0.0 | 2026-11-07 | Ratificação inicial | Primeira constituição do projeto, com 7 princípios, escopo e governança |
| 2.0.0 | 2026-11-07 | MAJOR | Redefinição de MUSTs nos Princípios II, III e V para refletir a spec aprovada |

## 2. Emenda 2.0.0

### 2.1 Princípio II — Integridade das Votações

**Motivação**: a spec aprovada permite que o administrador exclua uma cédula enquanto a
votação está aberta, após o que o participante pode votar novamente.

**Decisão**: a regra de cédula definitiva continua valendo para o participante, com exceção
operacional explícita para exclusão administrativa enquanto a votação está aberta. A exclusão
não acessa as escolhas e não é permitida após o encerramento.

### 2.2 Princípio III — Privacidade das Cédulas

**Motivação**: a combinação de exclusão administrativa com resultados agregados pode permitir
inferência das escolhas por comparação antes/depois.

**Decisão**: o risco residual de inferência por comparação manual de agregados é explicitamente
aceito. Mitigações obrigatórias:

- a interface não exibe diferenças de agregados antes/depois da exclusão;
- logs não registram escolhas;
- a exclusão ocorre em fluxo dedicado;
- testes de privacidade cobrem a ausência de escolhas nas respostas administrativas.

### 2.3 Princípio V — Segurança Proporcional

**Motivação**: a spec aprovada define username-only para participantes e senha para
administradores.

**Decisão**: os níveis de assurance são separados:

- autenticação administrativa exige senha;
- acesso de participante por username é baixa garantia em comunidade fechada, não é
  apresentado como autenticação forte e deve ter a limitação documentada na interface e na
  documentação.

## 3. Reconciliações de especificação

| Item | Decisão | Referência |
|---|---|---|
| FR-092 / fonte do catálogo | GameTora é referência de curadoria; importação de arquivo é o caminho operacional do MVP | `spec.md` FR-092 e premissas |
| FR-076 / exclusão após encerramento | Bloqueio é para exclusão individual; cancelamento em qualquer estado apaga todas as cédulas | `spec.md` FR-076, `data-model.md` §11 |
| Q2 / janela perdida | Votação nunca aberta é cancelada; votação já aberta é encerrada ao recuperar | `spec.md` Clarifications |
| FR-129 / dashboard | Indicadores definidos: participantes, votações, catálogo, imagens e últimas votações | `spec.md` FR-129 |
| G5 / licença de imagens | Revisão manual antes de `--apply`; sem gate técnico no MVP | `spec.md` premissas, `docs/operations.md` |
| I2 / datas de votação | Datas obrigatórias nos modos automáticos; informativas/opcionais nos modos manuais | `spec.md` FR-026, `data-model.md` §7.1 |
| A1 / admin participante | Admin vota como participante; cédula própria acessível somente pela rota de participante; visões administrativas nunca expõem escolhas | `spec.md` FR-011/FR-070/FR-079, `plan.md` Security Plan |

## 4. Riscos aceitos

| Risco | Decisão | Mitigação/documentação |
|---|---|---|
| G5 — licença de imagens sem gate técnico | Revisão manual obrigatória antes de `--apply` | `docs/operations.md`, `contracts/import-formats.md`, `contracts/management-commands.md` |
| M3 — cadastro público/exibição de username sem teste dedicado | Revisão manual de código e checklist | `docs/security-review.md` |
| C3 — inferência por comparação de agregados | Aceito na emenda 2.0.0 | Sem diff na UI, logs sem escolhas, teste de privacidade |

## 5. Medições manuais adotadas

| Critério | Forma de verificação | Registro |
|---|---|---|
| SC-001 — criar/configurar/agendar <5 min | Medição cronometrada no quickstart | `docs/operations.md` |
| SC-002 — concluir cédula <3 min | Medição cronometrada no quickstart | `docs/operations.md` |
| SC-010 — busca/filtros <1 s com 500 personagens | Medição manual documentada | `docs/operations.md` |

## 6. Referências

- `.specify/memory/constitution.md`
- `specs/001-character-ban-voting/spec.md`
- `specs/001-character-ban-voting/plan.md`
- `docs/security-review.md`
- `docs/operations.md`
