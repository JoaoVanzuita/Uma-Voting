# Quickstart: Validação do Uma Voting

**Feature**: `001-character-ban-voting`
**Date**: 2026-11-07
**Objetivo**: permitir que uma pessoa valide o MVP de ponta a ponta após a implementação.

## 1. Pré-requisitos

- Docker Engine 27+ e Docker Compose v2.
- Acesso à internet apenas para build inicial de imagens; a aplicação em execução não
  depende de serviços externos para imagens ou catálogo.
- Porta 8000 (desenvolvimento) ou 80/443 (produção) disponível.
- Um domínio apontando para o host, para validar HTTPS em produção.

## 2. Preparação do ambiente

```bash
cp .env.example .env
# editar .env com segredos locais
docker compose up --build
```

Em desenvolvimento, o `compose.override.yaml` usa Django `runserver` e expõe a porta 8000.
Em produção, use `docker compose -f compose.yaml -f compose.prod.yaml up -d --build`.

## 3. Inicialização

```bash
# migrations, collectstatic e cache table são executados pelo serviço release
docker compose run --rm release

# criar administrador inicial
docker compose exec web python manage.py create_admin --username admin

# validar catálogo/imagens (opcional no primeiro uso)
docker compose exec web python manage.py validate_images --json
```

Acesse:

- Participante: `http://localhost:8000/entrar/`
- Administrador: `http://localhost:8000/admin/entrar/`

## 4. Dados mínimos para validação

1. Crie participantes em `/admin/participantes/` (ou importe `participants.csv`).
2. Importe um catálogo pequeno com pelo menos 4 personagens e 5 versões:
   `python manage.py import_catalog --file catalog.csv --source curadoria-local --apply`.
3. Se houver imagens locais, importe pelo manifesto:
   `python manage.py import_images --manifest images.csv --source-dir ./assets-source --apply`.
4. Crie uma votação em `/admin/votacoes/nova/` com 3 escolhas, corte padrão e abertura
   manual.

## 5. Cenários de validação

### 5.1 Acesso e sessão

1. Abrir `/entrar/` e informar um username ativo.
2. Confirmar que a página inicial mostra apenas votações elegíveis; sem votações, exibe um
   estado vazio simples.
3. Fazer logout por POST e confirmar que a área protegida redireciona para o login.
4. Fechar e reabrir o navegador; confirmar que é necessário autenticar novamente.
5. Tentar entrar com username inexistente; confirmar mensagem de acesso negado.
6. Tentar entrar com username de administrador em `/entrar/`; confirmar que é rejeitado e
   que o login administrativo exige senha.
7. Confirmar que a página de login de participante exibe o aviso: “Este acesso identifica
   apenas o username; não comprova sua identidade.”

**Referências**: `contracts/http-routes.md`, `data-model.md` §3.

### 5.2 Participantes e elegibilidade

1. Cadastrar um participante novo; confirmar username único case-insensitive.
2. Criar uma votação; confirmar que todos os participantes ativos foram incluídos.
3. Adicionar/remover elegíveis em rascunho; confirmar que a lista muda.
4. Agendar ou abrir a votação; confirmar que a elegibilidade não pode mais ser editada.
5. Desativar um participante; confirmar que ele não autentica e que votações existentes
   não mudam.

**Referências**: `data-model.md` §7.2, `contracts/domain-services.md` §3.

### 5.3 Catálogo e data de corte

1. Importar catálogo com personagens lançadas e não lançadas no Global.
2. Confirmar que a importação de arquivo é o caminho operacional e que o GameTora é a
   referência de curadoria (FR-092).
3. Criar votação com data de corte que exclua as não lançadas.
4. Abrir a votação e confirmar que apenas personagens com versão
   `release_date_global <= cutoff` aparecem.
5. Alterar o catálogo depois da abertura; confirmar que a votação não muda.
6. Aprovar uma mudança pendente; confirmar que uma nova votação usa os novos dados e a
   antiga permanece igual.

**Referências**: `contracts/import-formats.md` §2, `data-model.md` §8.

### 5.4 Filtros e seleção

1. Na votação aberta, buscar por parte do nome; confirmar resposta instantânea.
2. Selecionar `Front` + `Sprint` + `Turf`; confirmar que só aparecem personagens com uma
   mesma versão que atenda a todos os critérios.
3. Selecionar dois valores na mesma categoria; confirmar comportamento OU.
4. Confirmar que uma personagem com várias versões aparece uma única vez.
5. Tentar selecionar a mesma personagem duas vezes; confirmar bloqueio.
6. Selecionar exatamente 3 personagens; confirmar contador "3 de 3".
7. Tentar confirmar com 2 escolhas; confirmar erro de servidor.

**Referências**: `contracts/domain-services.md` §4.6, §7.

### 5.5 Envio e privacidade da cédula

1. Revisar escolhas e confirmar o aviso de cédula definitiva.
2. Confirmar o envio; verificar feedback de sucesso.
3. Consultar a própria cédula; confirmar que as escolhas aparecem.
4. Tentar enviar novamente; confirmar 409 "já votou".
5. Como administrador, abrir resultados e participação; confirmar que vê apenas
   agregados e quem votou/não votou, nunca as escolhas.
6. Como participante, tentar acessar resultados durante a votação; confirmar bloqueio.
7. Como administrador elegível, votar no modo participante; confirmar que o voto conta, que a
   cédula própria é acessível somente pela rota de participante e que nenhuma tela administrativa
   exibe escolhas, inclusive as do próprio administrador.

**Referências**: `contracts/http-routes.md` §3, `data-model.md` §9–10.

### 5.6 Exclusão administrativa

1. Com a votação aberta, excluir a cédula de um participante pelo admin.
2. Confirmar que a cédula deixa de contar em resultados e participação, que o admin não vê
   as escolhas e que nenhuma tela exibe diferença de agregados antes/depois.
3. Confirmar que o participante pode votar novamente.
4. Encerrar a votação; tentar excluir uma cédula; confirmar bloqueio.
5. Cancelar a votação; confirmar que todas as cédulas foram eliminadas e que ela não
   aparece para participantes.

**Referências**: `contracts/domain-services.md` §7.3, §6.6.

### 5.7 Agendamento e recuperação

1. Criar votação com abertura e encerramento automáticos em poucos minutos.
2. Parar o serviço `web`, manter o `scheduler` (ou parar ambos e reiniciar).
3. Confirmar abertura/encerramento dentro de 1 minuto do horário.
4. Simular janela inteira perdida (horários no passado); confirmar cancelamento sem
   cédulas.
5. Simular votação aberta com encerramento perdido; confirmar encerramento ao recuperar.
6. Criar votação agendada sem elegíveis; confirmar cancelamento automático.
7. Criar duas votações abertas simultâneas; confirmar elegibilidades e cédulas
   independentes.
8. Criar votação com abertura e encerramento manuais, sem datas informativas; confirmar que a
   configuração é aceita e que as ações manuais funcionam.

**Referências**: `contracts/management-commands.md` §9–10, `data-model.md` §11.

### 5.8 Resultados e empates

1. Registrar votos de forma que duas personagens empatem em 2º e duas em 3º.
2. Encerrar a votação.
3. Confirmar ranking `1º, 2º, 2º, 3º, 3º` (dense rank).
4. Confirmar que personagens com zero votos não aparecem.
5. Confirmar que não há desempate por nome.
6. Consultar a própria cédula após o encerramento.

**Referências**: `research.md` §8, `contracts/domain-services.md` §8.

### 5.9 Imagens

1. Remover temporariamente um arquivo de imagem referenciado.
2. Confirmar que a interface exibe o placeholder e a personagem continua votável.
3. Executar `validate_images`; confirmar que a personagem é listada como sem imagem
   válida.
4. Substituir a imagem de uma personagem; confirmar que a votação antiga continua
   exibindo a imagem do snapshot e que a nova votação usa a nova.
5. Confirmar que nenhuma requisição externa de imagem ocorre durante a votação (aba de
   rede do navegador).
6. Antes de `import_images --apply` com fonte externa, confirmar que a licença foi revisada
   e registrada no runbook; o MVP não aplica gate técnico.

**Referências**: `data-model.md` §5, `contracts/management-commands.md` §7–8.

### 5.10 Medições de aceitação

1. **SC-001**: medir o tempo de um administrador criar, configurar e agendar uma votação
   completa; registrar duração e confirmar <5 min.
2. **SC-002**: medir o tempo de um participante elegível concluir uma cédula; registrar
   duração e confirmar <3 min.
3. **SC-010**: com 500 personagens, medir busca por nome e combinação de filtros; registrar
   duração e confirmar <1 s.
4. Registrar data, operador, ambiente e resultado em `docs/operations.md`.

### 5.11 Painel administrativo

1. Abrir o dashboard como administrador.
2. Confirmar os indicadores: total de participantes ativos, votações abertas, votações
   agendadas, mudanças de catálogo pendentes, imagens ausentes/inválidas e últimas votações.
3. Confirmar que os atalhos administrativos estão visíveis e acessíveis por teclado.

## 6. Testes automatizados

```bash
# lint/format
docker compose exec web ruff check .
docker compose exec web ruff format --check .

# testes (PostgreSQL real)
docker compose exec web pytest

# verificação de deploy
docker compose exec web python manage.py check --deploy --settings=config.settings.prod

# E2E opcional (se configurado)
docker compose exec web pytest -m e2e
```

- Testes usam PostgreSQL; SQLite não é suportado.
- Testes de concorrência e tempo são obrigatórios para os fluxos críticos.
- Testes de privacidade verificam que nenhuma página administrativa expõe escolhas.

## 7. Resultado esperado

O MVP está validado quando:

- todos os cenários acima passam;
- `pytest` está verde;
- `check --deploy` não reporta erros;
- `validate_images` identifica ausências sem quebrar a interface;
- o agendador funciona com o serviço web parado;
- backups de banco e mídia podem ser restaurados em um ambiente limpo.

## 8. Solução de problemas

| Sintoma | Verificação |
|---|---|
| Imagens não aparecem | `MEDIA_ROOT`, volume `media_data`, Caddy `/media/*`, status do asset |
| Estáticos sem estilo | `collectstatic`, volume `static_data`, Caddy `/static/*` |
| Scheduler não abre votações | logs do container `scheduler`, lock, `opens_at`, timezone |
| Login administrativo falha | `is_admin`, senha, throttle, `AUTHENTICATION_BACKENDS` |
| Login de participante rejeitado | usuário ativo e não admin; throttle |
| Erro de trigger no cancelamento | ordem status=`cancelled` → delete ballots na mesma transação |
| Migração falha | banco na versão esperada, backup antes do release |
