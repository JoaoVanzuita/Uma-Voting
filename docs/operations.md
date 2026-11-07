# Operações — Uma Voting

**Data**: 2026-11-07
**Constituição**: 2.0.0

## 1. Ambientes

- **Desenvolvimento**: Docker Compose com `compose.override.yaml`, Django `runserver` e
  PostgreSQL local.
- **Produção**: `compose.yaml` + `compose.prod.yaml`, Gunicorn, scheduler, Caddy e PostgreSQL.
- **Variáveis**: `.env` não versionado; consulte `.env.example`.

## 2. Deploy e release

```bash
docker compose -f compose.yaml -f compose.prod.yaml build
docker compose -f compose.yaml -f compose.prod.yaml run --rm release
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

O serviço `release` executa `migrate`, `collectstatic` e `createcachetable` uma vez. Migrations
não rodam no entrypoint de cada worker.

## 3. Scheduler e sincronização

- **Transições de votação**: container `scheduler` executa
  `python manage.py run_scheduler --interval 60`.
- **Sincronização de catálogo**: cron/systemd diário às 03:00 chamando `scripts/sync_catalog.sh`;
  o scheduler de votos não sincroniza catálogo.
- **Sessões**: `clearsessions` diário via cron/systemd.
- **Idempotência**: transições usam lock de banco e podem ser repetidas com segurança.

## 4. Backups e restauração

```bash
# banco
pg_dump -Fc -d "$DATABASE_URL" -f backup-$(date +%F).dump

# mídia
tar -czf media-$(date +%F).tar.gz media/

# restauração (ambiente limpo)
pg_restore -d "$DATABASE_URL" backup-YYYY-MM-DD.dump
tar -xzf media-YYYY-MM-DD.tar.gz
```

- Retenção: 30 backups diários + 12 mensais, fora do host.
- Testar restauração trimestralmente em ambiente limpo.
- Incluir banco e `media/` no mesmo procedimento.

## 5. Revisão manual de licença de imagens

Antes de aplicar um manifesto externo:

1. Conferir origem, termos e autorização de uso.
2. Registrar a decisão no runbook/checklist.
3. Só então executar `import_images --apply`.
4. O MVP não bloqueia tecnicamente a importação; a revisão é responsabilidade administrativa
   (risco G5 aceito).

## 6. Medições de aceitação

| Critério | Procedimento | Meta |
|---|---|---|
| SC-001 | Cronometrar admin criando, configurando e agendando uma votação | <5 min |
| SC-002 | Cronometrar participante concluindo uma cédula | <3 min |
| SC-010 | Medir busca/filtros com 500 personagens | <1 s |

Registrar data, operador, ambiente e duração neste documento.

## 7. Saúde, logs e monitoramento

- Healthcheck: `GET /health/` (aplicação + banco).
- Logs em stdout com request ID; rotação pelo Docker.
- Monitorar uptime, disco, último backup e erros 5xx.
- Não registrar escolhas de cédula, senhas ou corpos de confirmação.

## 8. Rollback e incidentes

1. Interromper o tráfego ou colocar em manutenção.
2. Restaurar a imagem/tag anterior.
3. Restaurar banco/mídia se houver migração ou corrupção.
4. Validar health, login, votação e resultados.
5. Registrar o incidente e a causa.

## 9. Rotação de segredos

- Rotacionar `SECRET_KEY` com janela de manutenção e invalidação de sessões.
- Rotacionar credenciais de banco e do proxy.
- Nunca commitar `.env` ou certificados privados.
