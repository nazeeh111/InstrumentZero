/** Configuration/result integrity in the actual validation UI.
 * Uses a generated minimal UI-response fixture and mocked DOM/network APIs.
 * No hardware, authentic-source inference, or physical accuracy is tested here.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../src/instrumentzero/web/validation.js', import.meta.url), 'utf8');

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}

function generatedUIBundle() {
  const initial = {quantity: {value: 100, interval_95: [80, 120]}, samples: 3,
    fit: {x: [0, .001, .002], observed: [0, .1, .2], predicted: [0, .1, .2]}};
  return {measurement_budget: 4, policy: 'information_gain', provenance: {random_seed: 0},
    initial_result: initial, stages: [{stage: 'initial_inference', result: initial},
      {stage: 'next_record_selected', selection: {point: 5, displacement_m: .003,
        gaussian_stiffness_variance_reduction_proxy: 4}}],
    reference_check: {held_out_points: 4, rmse_reference_force_n: .02},
    initial_reference_check: {rmse_reference_force_n: .03}};
}

function harness(fetchImpl) {
  const elements = new Map(), requests = [], downloads = [];
  function element(id) {
    if (elements.has(id)) return elements.get(id);
    let html = '', text = '';
    const listeners = new Map();
    const item = {id, disabled: false, hidden: false, value: '', listeners,
      addEventListener(type, callback) { listeners.set(type, callback); },
      get innerHTML() { return html; },
      set innerHTML(value) { html = String(value); text = html.replace(/<[^>]*>/g, ''); },
      get textContent() { return text; },
      set textContent(value) { text = String(value); html = text; }};
    elements.set(id, item);
    return item;
  }
  element('replay-budget').value = '4';
  element('replay-policy').value = 'information_gain';
  const context = {
    document: {getElementById: element, querySelector: () => element('validation-navigation'),
      createElement: () => ({href: '', download: '', click() { downloads.push(this.download); }})},
    fetch: async url => { requests.push(url); return fetchImpl(url); },
    lineChart: container => { element(container).innerHTML = '<svg data-generated-ui-fixture="true"></svg>'; },
    URL: {createObjectURL: () => 'blob:generated-ui-fixture', revokeObjectURL() {}},
    setTimeout() {}, console
  };
  vm.createContext(context);
  vm.runInContext(source, context, {filename: 'validation.js'});
  return {element, requests, downloads,
    dispatch(id, type = 'click') {
      const callback = element(id).listeners.get(type);
      assert.equal(typeof callback, 'function', `${id} must handle ${type}`);
      return callback({target: element(id)});
    }};
}

const response = bundle => ({ok: true, json: async () => bundle});
async function flush() { for (let i = 0; i < 12; i++) await Promise.resolve(); }

test('actual replay UI locks configuration during a deferred request and restores it after render', async () => {
  const pending = deferred(), h = harness(() => pending.promise);
  const running = h.dispatch('replay-load');
  assert.equal(h.element('replay-load').disabled, true);
  assert.equal(h.element('replay-budget').disabled, true);
  assert.equal(h.element('replay-policy').disabled, true);
  assert.equal(h.element('replay-next').disabled, true);
  assert.equal(h.element('replay-export').disabled, true);
  assert.equal(h.element('replay-summary').textContent, '');
  assert.deepEqual(h.requests, ['/api/replay?budget=4&policy=information_gain&seed=0']);
  pending.resolve(response(generatedUIBundle()));
  await running;
  for (const id of ['replay-load', 'replay-budget', 'replay-policy', 'replay-export']) {
    assert.equal(h.element(id).disabled, false, `${id} should be restored after this request`);
  }
  assert.match(h.element('replay-summary').textContent, /3 observed records/);
  assert.match(h.element('replay-stages').textContent, /initial inference/);
});

for (const [id, value] of [['replay-budget', '5'], ['replay-policy', 'fixed_uniform']]) {
  test(`editing ${id} clears old evidence and prevents stale replay export`, async () => {
    const h = harness(async () => response(generatedUIBundle()));
    await h.dispatch('replay-load');
    h.dispatch('replay-next');
    assert.match(h.element('replay-stage-detail').textContent, /Gaussian design-proxy/);
    h.element(id).value = value;
    h.dispatch(id, 'change');
    for (const item of ['replay-stages', 'replay-summary', 'replay-stage-detail']) {
      assert.equal(h.element(item).textContent, '', `${item} must not describe the old configuration`);
    }
    assert.match(h.element('replay-chart').textContent, /Start the recorded replay for these settings/);
    assert.equal(h.element('replay-next').disabled, true);
    assert.equal(h.element('replay-export').disabled, true);
    const requestsBefore = h.requests.length;
    // Invoke even a disabled control's handler to verify the state guard itself.
    h.dispatch('replay-next');
    h.dispatch('replay-export');
    await flush();
    assert.equal(h.requests.length, requestsBefore, 'No stale export should be requested');
    assert.equal(h.downloads.length, 0);
    assert.match(h.element('validation-message').textContent, /Start and inspect a recorded replay/);
  });
}

test('failed replay load restores controls while keeping evidence and export unavailable', async () => {
  const pending = deferred(), h = harness(() => pending.promise);
  const running = h.dispatch('replay-load');
  pending.reject(new Error('Generated network failure'));
  await running;
  assert.equal(h.element('replay-budget').disabled, false);
  assert.equal(h.element('replay-policy').disabled, false);
  assert.equal(h.element('replay-load').disabled, false);
  assert.equal(h.element('replay-export').disabled, true);
  assert.equal(h.element('replay-summary').textContent, '');
  assert.match(h.element('validation-message').textContent, /Generated network failure/);
});

test('replay export uses the loaded bundle configuration, independently of transient form values', async () => {
  const h = harness(async url => url.startsWith('/api/replay/export')
    ? {ok: true, blob: async () => new Uint8Array([1, 2, 3])}
    : response(generatedUIBundle()));
  await h.dispatch('replay-load');
  // Programmatic edits do not fire change; export still must not build a new unseen configuration.
  h.element('replay-budget').value = '5';
  h.element('replay-policy').value = 'fixed_uniform';
  h.dispatch('replay-export');
  await flush();
  assert.equal(h.requests.at(-1), '/api/replay/export?budget=4&policy=information_gain&seed=0');
  assert.deepEqual(h.downloads, ['instrumentzero-recorded-replay.zip']);
});
