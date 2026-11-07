# Revisão de Segurança e Privacidade — Uma Voting

**Data de referência**: 2026-11-07
**Constituição**: 2.0.0
**Status**: checklist para revisão antes do deploy; preencher durante a implementação.

## 1. Autenticação e sessão

- [ ] Administrador autentica com username + senha; senha com hash do Django.
- [ ] Participante autentica somente por username, com mensagem genérica de falha.
- [ ] Username de administrador é rejeitado no fluxo de participante.
- [ ] Sessão expira ao fechar o navegador e por logout POST.
- [ ] Cookies de sessão são `HttpOnly`, `Secure` em produção e `SameSite=Lax`.
- [ ] CSRF está ativo em todos os POSTs, incluindo HTMX.
- [ ] Throttle de login por IP/username com `DatabaseCache`.
- [ ] Não existe rota pública de cadastro.

## 2. Autorização

- [ ] Rotas administrativas exigem `is_admin=True` no servidor.
- [ ] Rotas de votação verificam elegibilidade do participante.
- [ ] Cédula própria é filtrada por `request.user`, inclusive para administrador no modo
      participante.
- [ ] Administrador em modo participante não perde autorização administrativa, mas a UI
      participante não expõe agregados durante a votação.
- [ ] Nenhuma view administrativa importa `BallotChoice`.

## 3. Privacidade das cédulas

- [ ] Resultados administrativos são agregados e não contêm `participant_id`.
- [ ] Participação contém apenas username e indicador votou/não votou.
- [ ] Exclusão administrativa localiza a cédula por votação + participante, sem ler escolhas.
- [ ] A UI não exibe diferença de agregados antes/depois da exclusão.
- [ ] Logs não registram escolhas, corpo do POST de confirmação ou dumps de cédulas.
- [ ] Testes verificam que páginas administrativas não exibem associações participante–personagem.
- [ ] Administrador no modo participante acessa somente a própria cédula; nenhuma visão
      administrativa expõe escolhas de outros participantes nem as do próprio admin.
- [ ] Risco residual de inferência por comparação manual de agregados está documentado na
      emenda 2.0.0.

## 4. Apresentação e privacidade de identidade

- [ ] A interface exibe somente o username do participante, sem e-mail, nome legal ou outros
      dados pessoais.
- [ ] A página de login de participante exibe: “Este acesso identifica apenas o username; não
      comprova sua identidade.”
- [ ] Não há cadastro público; a ausência de rotas é verificada por revisão de código.

## 5. Imagens e licenças

- [ ] Imagens são armazenadas localmente em `media/characters/`.
- [ ] A aplicação não faz requisições externas de imagem em runtime.
- [ ] Importação externa exige revisão manual de licença registrada no runbook antes de
      `import_images --apply`.
- [ ] O MVP não aplica gate técnico de licença (risco G5 aceito); a limitação está documentada.
- [ ] Imagens ausentes/inválidas usam placeholder e não bloqueiam a personagem.
- [ ] Arquivos antigos não são removidos enquanto snapshots dependerem deles.

## 6. Infraestrutura e operação

- [ ] HTTPS com Caddy; HSTS, cookies seguros e redirecionamento.
- [ ] CSP com `script-src 'self'`; sem scripts inline próprios.
- [ ] `SECRET_KEY` e credenciais fora do repositório.
- [ ] Banco e `media/` cobertos por backup; restore testado.
- [ ] Logs sem dados sensíveis; request ID; rotação de logs.
- [ ] Dependências auditadas e patches aplicados.
- [ ] Acesso ao banco e backups restrito a operadores confiáveis.

## 7. Riscos aceitos

- **G5**: revisão manual de licença de imagens, sem gate técnico no MVP.
- **M3**: ausência de teste dedicado para cadastro público/exibição de username; revisão manual.
- **C3**: inferência por comparação de agregados; mitigação e aceite na emenda 2.0.0.
