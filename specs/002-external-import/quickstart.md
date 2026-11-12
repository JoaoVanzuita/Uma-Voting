# Quickstart: Validação da Importação Externa

**Feature**: `002-external-import`
**Date**: 2026-11-12
**Objetivo**: validar o fluxo completo de importação de catálogo e imagens pela interface, sem
arquivos e sem acesso ao shell para a operação normal.

## 1. Pré-requisitos

- Docker Engine 27+ e Docker Compose v2.
- Saída HTTPS do container `import-worker` para:
  - `en-portal.g.kuroco.app`
  - `en-portal.g.kuroco-img.app`
  - `umamusume.com`
  - `gametora.com`
- Um administrador cadastrado.
- `EXTERNAL_IMPORT_ENABLED=True` no ambiente.

## 2. Preparação

```bash
cp .env.example .env
# revisar EXTERNAL_IMPORT_* e segredos

docker compose up -d --build
docker compose run --rm release
```

O serviço `release` executa `migrate`, `collectstatic` e `createcachetable`. As migrations
`0004`, `0005` e `0006` criam `ImportJob`, os campos novos, as constraints, a fonte
`umamusume-global` e os triggers de imutabilidade terminal.

## 3. Subir o worker

```bash
docker compose up -d import-worker
docker compose logs -f import-worker
```

O worker fica ocioso até existir uma execução na fila. Não é necessário cron.

## 4. Criar o administrador (se ainda não existir)

```bash
docker compose exec web python manage.py create_admin --username admin
```

Acesse `http://localhost:8000/admin/entrar/`.

## 5. Verificar a fonte

1. Abra `/admin/catalogo/`.
2. No painel "Fontes externas", confirme:
   - `umamusume-global` listada;
   - situação habilitada;
   - nota de licença visível;
   - conector reconhecido.
3. Clique em "Verificar fonte".
4. Resultado esperado: "Fonte disponível."

O painel mostra todas as fontes cadastradas, inclusive desabilitadas ou sem conector, com o
motivo. O seletor do formulário de importação lista apenas fontes habilitadas com conector.

Se a fonte não aparecer, confira a migration `0005` e o registry do conector.

## 6. Importar catálogo e imagens

1. Abra `/admin/catalogo/importar/`.
2. Selecione:
   - Fonte: `umamusume-global`;
   - Modo: `Catálogo + imagens`;
   - Escopo: `Apenas personagens sem imagem válida` (primeira carga: equivalente a todas).
3. Marque a confirmação de licença.
4. Clique em "Iniciar importação".
5. Você será redirecionado para `/admin/catalogo/importacoes/<id>/`.
6. Acompanhe fase, progresso e passo atual. A página atualiza automaticamente a cada 3 segundos.

### O que esperar

- Fase `catalog`: coleta oficial + GameTora, aplicação atômica.
- Fase `images`: download, validação, normalização WebP 256×256 e associação.
- Status final:
  - `success`: tudo aplicado;
  - `partial`: catálogo aplicado, algumas imagens falharam;
  - `failed`: catálogo não aplicado ou fonte indisponível;
  - `cancelled`: interrompido pelo administrador.

## 7. Validar o resultado

### Pela interface

- `/admin/catalogo/personagens/`: personagens importadas.
- `/admin/catalogo/imagens/`: assets, situação e personagens sem imagem.
- `/admin/catalogo/importacoes/`: histórico.
- Detalhe da execução: contagens, avisos, erros e link para o `SyncRun`.

### Pelo shell (opcional)

```bash
docker compose exec web python manage.py shell -c "
from apps.catalog.models import Character, CharacterVersion, ImageAsset, ImportJob
print('personagens:', Character.objects.count())
print('versões:', CharacterVersion.objects.count())
print('imagens:', ImageAsset.objects.count())
print('jobs:', list(ImportJob.objects.values_list('id', 'status')))
"
```

Esperado para o catálogo atual:

- 85 personagens;
- 85 versões;
- 85 imagens correntes válidas, salvo erros reportados.

### Validar imagens

```bash
docker compose exec web python manage.py validate_images --json
```

### Validar snapshots e isolamento

- Abra uma votação existente com snapshot e confirme que personagens, versões e resultados
  permanecem idênticos após a importação.
- Nas páginas de participante e catálogo, confira no navegador que as imagens são servidas por
  `/media/` e que não há requisições externas de imagem.

## 8. Testar idempotência

1. Inicie uma segunda importação completa.
2. Resultado esperado:
   - 0 personagens duplicadas;
   - 0 versões duplicadas;
   - imagens reutilizadas por checksum;
   - status `success` ou `partial` apenas por erros de rede.

## 9. Testar cancelamento

1. Inicie uma importação completa.
2. Clique em "Cancelar" durante a fase de imagens.
3. Resultado esperado:
   - status `cancelled`;
   - catálogo já aplicado permanece;
   - imagens já gravadas permanecem;
   - o restante não é baixado.

Na fase de catálogo, o cancelamento é verificado antes da aplicação: a coleta em curso termina,
mas nenhuma alteração é gravada depois da solicitação.

## 10. Testar falha e repetição

1. Desconecte a rede do container `import-worker` ou use uma fonte indisponível.
2. Inicie uma importação.
3. Resultado esperado:
   - `failed` com mensagem clara;
   - nenhuma alteração parcial de catálogo.
4. Restaure a rede e clique em "Repetir".
5. Resultado esperado: nova execução, sem alterar a anterior.

## 11. Testar o kill switch

```bash
# no .env
EXTERNAL_IMPORT_ENABLED=False
```

Reinicie `web` e `import-worker`. A tela de importação deve indicar que a feature está
desabilitada e recusar novas execuções. O catálogo e as imagens existentes continuam funcionando.

## 12. Staging temporário

O banco de staging usa `config.settings.staging`:

```bash
DJANGO_SETTINGS_MODULE=config.settings.staging \
POSTGRES_HOST=172.22.0.2 POSTGRES_PORT=5432 \
STAGING_POSTGRES_DB=uma_voting_staging \
.venv/bin/python manage.py migrate
```

Para validar a importação externa no staging, suba o worker com o mesmo
`DJANGO_SETTINGS_MODULE` e o mesmo banco. O volume `media/` é compartilhado; checksums iguais
reutilizam o asset.

## 13. Solução de problemas

| Sintoma | Causa provável | Ação |
|---|---|---|
| Fonte não aparece | `adapter` vazio ou não registrado | Conferir migration e registry |
| "Importação externa desabilitada" | `EXTERNAL_IMPORT_ENABLED=False` | Ajustar `.env` e reiniciar |
| Botão de importar desabilitado | Fonte sem licença | Preencher `license_note` |
| Job fica `queued` | Worker não está rodando | `docker compose up -d import-worker` |
| Job fica `running` sem progresso | Worker caiu | Aguardar stale recovery ou reiniciar o worker |
| `failed` na fase de catálogo | Fonte oficial/GameTora indisponível ou mudou | Verificar fonte, logs e conector |
| `partial` com erros de imagem | Imagens 404/inválidas | Ver relatório; repetir ou corrigir a fonte |
| Imagens não aparecem | Asset inválido ou caminho ausente | Rodar `validate_images` |
| Muitos 429 | Rate limit da fonte | Reduzir concorrência e tentar novamente |

## 14. Critérios de aceite da validação

- [ ] A fonte `umamusume-global` aparece com licença e conector.
- [ ] A importação completa roda sem arquivo e sem shell.
- [ ] O progresso aparece em até 5 segundos.
- [ ] O catálogo é aplicado automaticamente e sem pendências.
- [ ] As imagens são baixadas, normalizadas e associadas.
- [ ] O relatório lista contagens, avisos e erros.
- [ ] A matriz erro × aviso está correta: falha sistêmica aborta; item 404/metadado ausente gera aviso.
- [ ] Snapshots, cédulas e resultados existentes permanecem inalterados.
- [ ] Páginas de participante não fazem requisições externas de imagem.
- [ ] O painel mostra fontes inelegíveis; o seletor lista apenas elegíveis.
- [ ] O catálogo não aplica alterações após cancelamento solicitado.
- [ ] As constraints e o trigger de `ImportJob` estão ativos.
- [ ] Uma segunda execução é idempotente.
- [ ] Cancelar preserva o que já foi aplicado.
- [ ] Repetir cria nova execução.
- [ ] Participantes continuam usando apenas mídia local.
