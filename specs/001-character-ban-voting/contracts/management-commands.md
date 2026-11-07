# Contract: Comandos de Gerenciamento

**Feature**: `001-character-ban-voting`
**Date**: 2026-11-07

## 1. Convenções

- Todos os comandos usam `python manage.py <comando>`.
- Saída em texto legível por padrão; `--json` quando indicado.
- Código de saída `0` em sucesso, `1` em erro de validação e `2` em erro inesperado.
- Comandos de importação suportam `--dry-run` (padrão) e `--apply` explícito.
- Nenhum comando grava escolhas de cédula em log.
- Comandos de dados rodam em transação quando aplicam alterações.

## 2. `create_admin`

Cria um administrador inicial.

```bash
python manage.py create_admin --username admin
```

- Solicita a senha interativamente ou aceita `--password-stdin`.
- Não aceita senha em argumento de linha de comando (evita histórico).
- Valida username único case-insensitive.
- Idempotente: se o usuário existir, falha com mensagem clara.

## 3. `import_participants`

Importa participantes de CSV.

```bash
python manage.py import_participants --file participants.csv --dry-run
python manage.py import_participants --file participants.csv --apply
```

- Formato em `contracts/import-formats.md`.
- `--dry-run` valida e mostra erros por linha; não grava.
- `--apply` é atômico: qualquer erro impede toda a importação.
- Saída: total de linhas, válidas, importadas, erros por linha.
- Exit code 1 se houver inconsistências.

## 4. `import_catalog`

Importa catálogo de CSV/JSON curado.

```bash
python manage.py import_catalog --file catalog.csv --source curadoria-local --dry-run
python manage.py import_catalog --file catalog.csv --source curadoria-local --apply
```

- Cria `SyncRun` e `SyncChange`.
- Novas personagens elegíveis: aplicadas automaticamente.
- Alterações em personagens existentes: pendentes de aprovação.
- `--dry-run` mostra a prévia completa (novas, pendentes, ignoradas, erros) sem gravar.
- `--apply` aplica apenas as novas personagens; mudanças existentes ficam pendentes.
- Exit code 1 se o arquivo for inválido; o catálogo não é alterado.

## 5. `sync_catalog`

Executa sincronização de uma fonte configurada.

```bash
python manage.py sync_catalog --source curadoria-local --file catalog.csv
```

- Equivalente ao `import_catalog --apply` para a fonte de arquivo.
- Adaptadores futuros (`gametora`, `umapyoi`) devem implementar a mesma interface e só
  podem ser habilitados após verificação de termos/autorização.
- A sincronização periódica padrão é diária às 03:00 em `America/Sao_Paulo`, além da
  execução manual.

## 6. `approve_catalog_change` / `reject_catalog_change`

Alternativa de linha de comando para a aprovação administrativa.

```bash
python manage.py approve_catalog_change --id 42 --reviewer admin
python manage.py reject_catalog_change --id 42 --reviewer admin --note "dados divergentes"
```

- Exige mudança `pending`.
- Aprovação aplica o payload em transação e registra revisor/timestamp.
- A interface administrativa é o caminho principal; os comandos servem para operação e
  testes.

## 7. `validate_images`

Valida o acervo local.

```bash
python manage.py validate_images --json
```

- Verifica:
  - arquivo existente;
  - formato permitido;
  - integridade via Pillow;
  - dimensões/proporção;
  - checksum;
  - associação com personagem;
  - arquivos órfãos;
  - referências quebradas;
  - duplicidades suspeitas;
  - personagens sem imagem válida.
- Atualiza `ImageAsset.status`, `validated_at`, `width`, `height`.
- Relatório com contagens e lista de problemas.
- Exit code 1 se houver imagens inválidas/corrompidas ou referências quebradas; imagens
  ausentes são avisos e só falham com `--strict`.

## 8. `import_images`

Importa ou substitui imagens a partir de um manifesto.

```bash
python manage.py import_images \
  --manifest images.csv \
  --source-dir ./assets-source \
  --dry-run
```

```bash
python manage.py import_images \
  --manifest images.csv \
  --source-dir ./assets-source \
  --apply
```

- Manifesto em `contracts/import-formats.md`.
- Normaliza para WebP 256 × 256 sem distorção (`ImageOps.pad`).
- Destino content-addressed: `media/characters/<stable_id>/<sha256>.webp`.
- `--dry-run` mostra inclusões, substituições, duplicidades e erros.
- `--apply` aplica cada item válido em transação própria; itens inválidos não são
  aplicados e o relatório lista o que foi aplicado.
- Imagem de fonte externa exige revisão manual de licença registrada no runbook antes de
  `--apply`; não há gate técnico de licença no MVP.
- Nunca sobrescreve arquivo existente; nunca apaga imagens antigas.
- Assets antigos permanecem referenciados por snapshots.

## 9. `process_voting_transitions`

Executa uma passagem do agendador.

```bash
python manage.py process_voting_transitions --now 2026-12-01T12:00:00-03:00
```

- Sem `--now`, usa o relógio do servidor.
- Idempotente.
- Adquire `pg_try_advisory_lock`; se outra execução estiver ativa, sai com código 0 e
  mensagem "já em execução".
- Processa aberturas/encerramentos/cancelamentos devidos.
- `--json` retorna `{processed, opened, closed, cancelled, errors}`.
- Nunca depende de navegador ou requisição de usuário.

## 10. `run_scheduler`

Loop do agendador para o container dedicado.

```bash
python manage.py run_scheduler --interval 60
```

- Executa `process_voting_transitions` a cada `interval` segundos.
- Trata `SIGTERM`/`SIGINT` para encerrar com segurança.
- Registra cada ciclo e erros em stdout.
- Não executa migrations nem collectstatic.

## 11. `clearsessions`

Comando nativo do Django, agendado diariamente:

```bash
python manage.py clearsessions
```

- Remove sessões expiradas.
- Pode ser chamado por cron/systemd ou pelo scheduler em um intervalo diário.

## 12. `seed_demo` (apenas desenvolvimento)

```bash
python manage.py seed_demo
```

- Cria dados fictícios para desenvolvimento/testes visuais.
- Recusa execução quando `DEBUG=False`.
- Nunca é executado em produção.
- Não usar nomes/imagens reais sem documentação de origem.

## 13. `check_deploy`

```bash
python manage.py check --deploy --settings=config.settings.prod
```

- Executado no CI e no release.
- Falha se configurações de segurança de produção estiverem ausentes.
