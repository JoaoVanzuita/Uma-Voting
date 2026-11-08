# Revisão de Segurança e Privacidade — Uma Voting

**Data de referência**: 2026-11-07
**Constituição**: 2.0.0
**Status**: revisado em 2026-11-07 durante a Fase 11. Itens verificados por revisão de código, testes automatizados, `check --deploy` e auditoria de dependências.

## 1. Autenticação e sessão

- [x] Administrador autentica com username + senha; senha com hash do Django.
- [x] Participante autentica somente por username, com mensagem genérica de falha.
- [x] Username de administrador é rejeitado no fluxo de participante.
- [x] Sessão expira ao fechar o navegador e por logout POST.
- [x] Cookies de sessão são `HttpOnly`, `Secure` em produção e `SameSite=Lax`.
- [x] CSRF está ativo em todos os POSTs, incluindo HTMX.
- [x] Throttle de login por IP/username com `DatabaseCache`.
- [x] Não existe rota pública de cadastro.

## 2. Autorização

- [x] Rotas administrativas exigem `is_admin=True` no servidor.
- [x] Rotas de votação verificam elegibilidade do participante.
- [x] Cédula própria é filtrada por `request.user`, inclusive para administrador no modo
      participante.
- [x] Administrador em modo participante não perde autorização administrativa, mas a UI
      participante não expõe agregados durante a votação.
- [x] Nenhuma view administrativa importa `BallotChoice`.

## 3. Privacidade das cédulas

- [x] Resultados administrativos são agregados e não contêm `participant_id`.
- [x] Participação contém apenas username e indicador votou/não votou.
- [x] Exclusão administrativa localiza a cédula por votação + participante, sem ler escolhas.
- [x] A UI não exibe diferença de agregados antes/depois da exclusão.
- [x] Logs não registram escolhas, corpo do POST de confirmação ou dumps de cédulas.
- [x] Testes verificam que páginas administrativas não exibem associações participante–personagem.
- [x] Administrador no modo participante acessa somente a própria cédula; nenhuma visão
      administrativa expõe escolhas de outros participantes nem as do próprio admin.
- [x] Risco residual de inferência por comparação manual de agregados está documentado na
      emenda 2.0.0.

## 4. Apresentação e privacidade de identidade

- [x] A interface exibe somente o username do participante, sem e-mail, nome legal ou outros
      dados pessoais.
- [x] A página de login de participante exibe: “Este acesso identifica apenas o username; não
      comprova sua identidade.”
- [x] Não há cadastro público; a ausência de rotas é verificada por revisão de código.

## 5. Imagens e licenças

- [x] Imagens são armazenadas localmente em `media/characters/`.
- [x] A aplicação não faz requisições externas de imagem em runtime.
- [x] Importação externa exige revisão manual de licença registrada no runbook antes de
      `import_images --apply`.
- [x] O MVP não aplica gate técnico de licença (risco G5 aceito); a limitação está documentada.
- [x] Imagens ausentes/inválidas usam placeholder e não bloqueiam a personagem.
- [x] Arquivos antigos não são removidos enquanto snapshots dependerem deles.

## 6. Infraestrutura e operação

- [x] HTTPS com Caddy; HSTS, cookies seguros e redirecionamento.
- [x] CSP com `script-src 'self'`; sem scripts inline próprios.
- [x] `SECRET_KEY` e credenciais fora do repositório.
- [x] Banco e `media/` cobertos por backup; restore testado.
- [x] Logs sem dados sensíveis; request ID; rotação de logs.
- [x] Dependências auditadas e patches aplicados.
- [x] Acesso ao banco e backups restrito a operadores confiáveis.

## 7. Riscos aceitos

- **G5**: revisão manual de licença de imagens, sem gate técnico no MVP.
- **M3**: ausência de teste dedicado para cadastro público/exibição de username; revisão manual.
- **C3**: inferência por comparação de agregados; mitigação e aceite na emenda 2.0.0.


## 8. Evidências da revisão

- **Testes automatizados**: suíte completa com testes de autenticação, autorização,
  privacidade, triggers, concorrência e resultados.
- **Check de produção**: `python manage.py check --deploy --fail-level WARNING` sem avisos
  com as configurações de produção.
- **Auditoria de dependências**: `uv run --with pip-audit pip-audit` executado em 2026-11-07 — nenhuma
  vulnerabilidade conhecida encontrada.
- **CSP**: `script-src 'self'`, sem scripts inline; confirmação visual e por revisão.
- **Throttle**: limites por IP e username em `apps/accounts/services/throttle.py`.
- **Cadastro público**: ausência de rota verificada por revisão de `config/urls.py` e
  `apps/accounts/urls.py`.
- **Exibição de username**: templates exibem apenas `username`, sem e-mail ou nome legal.
- **Licença de imagens**: revisão manual registrada em `docs/operations.md` §5.
