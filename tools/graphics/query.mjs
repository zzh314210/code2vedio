import { query, providers } from 'graphics-api-remotion';

const request = JSON.parse(process.argv[2]);
const selected = request.providers ?? ['lucide'];
const result = [];
for (const source of selected) {
  if (!providers[source]) throw new Error(`Unknown graphics provider: ${source}`);
  if (['lucide', 'phosphor'].includes(source) && /^[a-z0-9-]+$/.test(request.keyword)) {
    try {
      result.push(await providers[source].get({name: request.keyword, color: request.color, weight: request.style ?? 'regular'}));
    } catch {}
  }
  if (!result.some(item => item.source === source)) {
    result.push(...await providers[source].search(request.keyword.split(/\s+/)));
  }
}
if (!result.length) {
  result.push(...(await query(request.keyword)).filter(item => selected.includes(item.source)));
}
process.stdout.write(JSON.stringify(result.filter(Boolean).slice(0, request.limit ?? 2)));
