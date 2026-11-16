import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';

const script = await readFile(new URL('../src/instrumentzero/web/runtime-version.js', import.meta.url), 'utf8');

async function render(fetch) {
  const badge = { textContent: 'Version unavailable' };
  Object.defineProperty(badge, 'innerHTML', { set() { throw new Error('unsafe HTML'); } });
  const document = { getElementById: id => id === 'runtime-version' ? badge : null };
  await runInNewContext(script, { document, fetch });
  return badge.textContent;
}

test('version badge displays the health version as text', async () => {
  assert.equal(await render(async () => ({ ok: true, json: async () => ({ version: '0.3.1.dev0' }) })), 'v0.3.1.dev0');
  assert.equal(await render(async () => ({ ok: true, json: async () => ({ version: '<img>' }) })), 'v<img>');
});

test('version badge retains its fallback when health is unavailable or malformed', async () => {
  for (const fetch of [
    async () => { throw new Error('offline'); },
    async () => ({ ok: false }),
    async () => ({ ok: true, json: async () => { throw new Error('invalid JSON'); } }),
    async () => ({ ok: true, json: async () => ({ version: '' }) }),
    async () => ({ ok: true, json: async () => ({ version: null }) }),
  ]) assert.equal(await render(fetch), 'Version unavailable');
});
