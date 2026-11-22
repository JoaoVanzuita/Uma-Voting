/**
 * Provisionamento do Railway — Infrastructure as Code (`.railway/railway.ts`).
 *
 *   npm install                          # SDK usado só para os tipos
 *   railway link --environment production
 *   railway config plan --show-values     # revisa, não altera nada
 *   railway config apply                  # cria Postgres, Bucket e o serviço web
 *   ./scripts/railway-provision.sh secrets  # segredos, hosts e CSP
 *
 * O serviço web compartilha um projeto com o banco e o bucket; o domínio
 * público é gerado pelo próprio `apply` (networking abaixo). Segredos nunca
 * ficam aqui: entram como `preserve()` e são gravados pela CLI.
 *
 * Importante: a CLI avalia este arquivo com o SDK `railway` instalado, e esse
 * pacote reexporta o próprio arquivo. Por isso o export default recebe de a
 * CLI o contexto e a fábrica de projeto; o `ctx` é exatamente o objeto de
 * `createRailwayContext` esperado pelas fábricas do SDK.
 */

import { bucket, github, postgres, preserve, ref, service } from "railway/iac";

export default <T,>(
  ctx: { environment?: string; projectName?: string },
  projectFactory: (name: string, definition: { resources: unknown[] }) => T,
): T => {
  // Um projeto por ambiente de deploy; o nome vem do contexto da CLI.
  const projectName = ctx.projectName ?? "uma-voting";

  // PostgreSQL gerenciado, com o volume persistente do template.
  const db = postgres("Postgres");

  // Bucket privado para media/ (S3-compatible, URLs assinadas).
  const media = bucket("uma-voting-media", { region: "iad" });

  const web = service("web", {
    source: github("JoaoVanzuita/Uma-Voting", { branch: "main" }),
    // Define a instância do serviço no ambiente e o domínio público. O Railway
    // injeta PORT=8080 no container e o Gunicorn escuta nela (CMD da imagem);
    // um domínio apontando para 8000 responde 502. Sem startCommand.
    networking: { serviceDomains: { web: { port: 8080 } } },
    // Build pelo Dockerfile da raiz (a validação do Dockerfile é a mesma do
    // build remoto; ver o histórico de `--mount` nas decisões do plano).
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    deploy: {
      // O schema do Railway aceita no máximo 1 item no preDeployCommand.
      preDeployCommand: ["sh scripts/railway-predeploy.sh"],
      preDeployTimeoutSeconds: 300,
      healthcheckPath: "/health/",
      healthcheckTimeout: 300,
      numReplicas: 1,
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 3,
    },
    variables: {
      DJANGO_SETTINGS_MODULE: { value: "config.settings.prod" },
      DJANGO_DEBUG: { value: "False" },
      DJANGO_LOG_LEVEL: { value: "INFO" },
      DJANGO_TIME_ZONE: { value: "America/Sao_Paulo" },
      DJANGO_DB_CONN_MAX_AGE: { value: "0" },
      GUNICORN_WORKERS: { value: "1" },
      STATIC_SERVE_WHITENOISE: { value: "True" },
      SECURITY_HEADERS_MODE: { value: "django" },
      DJANGO_SCHEDULER_MODE: { value: "on_request" },
      DJANGO_SCHEDULER_TICK_INTERVAL: { value: "60" },
      DJANGO_SECURE_REDIRECT_EXEMPT_HEALTH: { value: "True" },
      EXTERNAL_IMPORT_ENABLED: { value: "False" },
      MEDIA_STORAGE_BACKEND: { value: "s3" },
      AWS_S3_REGION_NAME: { value: "auto" },
      AWS_S3_ADDRESSING_STYLE: { value: "virtual" },
      AWS_QUERYSTRING_EXPIRE: { value: "3600" },
      // Referências entre serviços, resolvidas pelo Railway.
      DATABASE_URL: ref(db, "DATABASE_URL"),
      AWS_S3_ENDPOINT_URL: ref(media, "ENDPOINT"),
      AWS_ACCESS_KEY_ID: ref(media, "ACCESS_KEY_ID"),
      AWS_SECRET_ACCESS_KEY: ref(media, "SECRET_ACCESS_KEY"),
      AWS_STORAGE_BUCKET_NAME: ref(media, "BUCKET"),
      // Segredos e hosts: gravados fora do repositório (CLI/Dashboard).
      DJANGO_SECRET_KEY: preserve(),
      DJANGO_ALLOWED_HOSTS: preserve(),
      DJANGO_CSRF_TRUSTED_ORIGINS: preserve(),
      MEDIA_CSP_SOURCE: preserve(),
    },
  });

  return projectFactory(projectName, {
    resources: [web, db, media],
  });
};
