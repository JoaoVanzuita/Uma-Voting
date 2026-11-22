// Avaliação local do IaC (mesmo formato que a CLI produz), para conferir o
// plano antes de `railway config plan`. Roda com `npx tsx .railway/eval.mjs`.
const railwayTs = new URLSearchParams({ file: new URL("./railway.ts", import.meta.url).href }).get("file");
const mod = await import(`${railwayTs}?t=${Date.now()}`);
const exported = mod.default;
const projectFactory = (name, definition = {}) => {
  const resources = (definition.resources ?? definition.services ?? []).flat?.() ?? [];
  return { name, ...definition, resources };
};
const project = await exported({ environment: process.env.RAILWAY_ENVIRONMENT ?? "production" }, projectFactory);

const web = project.resources.find((resource) => resource.name === "Uma-Voting");
console.log(`projeto: ${project.name}`);
console.log(`recursos: ${project.resources.map((r) => `${r.type}.${r.name}`).join(", ")}`);
console.log(`deploy: ${JSON.stringify(web.deploy)}`);
console.log(`variáveis: ${Object.keys(web.variables).length}`);
for (const key of ["DATABASE_URL", "AWS_STORAGE_BUCKET_NAME", "DJANGO_SECRET_KEY"]) {
  console.log(`  ${key} = ${JSON.stringify(web.variables[key])}`);
}
