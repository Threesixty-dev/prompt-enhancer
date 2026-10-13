import { node, schemaField, validateForm } from './forms.js';

const $ = id => document.getElementById(id);
const json = value => JSON.stringify(value, null, 2);
const countLabel = (count, label) => count + ' ' + label + (count === 1 ? '' : 's');
const badge = value => node('span', value || 'unknown', 'badge ' + (value || 'unknown'));
const tell = message => { $('notice').textContent = message; };
const terminal = new Set(['succeeded', 'failed', 'cancelled', 'interrupted', 'superseded']);
let connected = false, experiments = [], runs = [], routeEpoch = 0;
let activeRoute, definition, runSchema, polling = false, refreshVersion = 0;
const snapshots = new WeakMap();

async function api(path, body) {
  const headers = { 'Content-Type': 'application/json' };
  const response = await fetch(path, { method: body === undefined ? 'GET' : 'POST', cache: 'no-store', credentials: 'same-origin', headers, body: body === undefined ? undefined : json(body) });
  if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Bench unavailable. Reload the page to reconnect.');
  const value = await response.json();
  if (!response.ok) { const error = new Error(value.error?.code || 'request_failed'); error.status = response.status; throw error; }
  return value;
}

function link(text, href, className) {
  const anchor = node('a', text, className); anchor.href = href; anchor.dataset.route = ''; return anchor;
}
const experimentPath = d => '/experiments/' + encodeURIComponent(d.stableId) + '?revision=' + encodeURIComponent(d.revision);
const newRunPath = (d, from) => '/experiments/' + encodeURIComponent(d.stableId) + '/runs/new?revision=' + encodeURIComponent(d.revision) + (from ? '&from=' + encodeURIComponent(from) : '');
const runPath = r => '/experiments/' + encodeURIComponent(r.stable_id) + '/runs/' + encodeURIComponent(r.id);
function metadata(values) { const element = node('div', undefined, 'meta'); for (const value of values.filter(Boolean)) element.append(node('span', value)); return element; }
function disclosure(title, content, key) {
  const element = node('details'); if (key) element.dataset.key = key;
  element.append(node('summary', title), content); return element;
}
const evidence = (title, value, key) => disclosure(title, node('pre', json(value)), key);
function patch(container, value, build) {
  const signature = json(value);
  if (snapshots.get(container) === signature) return;
  const open = new Set([...container.querySelectorAll('details[open][data-key]')].map(d => d.dataset.key));
  container.replaceChildren(build());
  for (const item of container.querySelectorAll('details[data-key]')) item.open = open.has(item.dataset.key);
  snapshots.set(container, signature);
}
function parseRoute() {
  const segments = location.pathname.split('/').filter(Boolean).map(decodeURIComponent), query = new URLSearchParams(location.search);
  if (!segments.length || (segments.length === 1 && segments[0] === 'experiments')) return { kind: 'list' };
  if (segments[0] !== 'experiments' || !/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$/.test(segments[1] || '')) return { kind: 'missing' };
  const base = { id: segments[1], revision: query.get('revision'), from: query.get('from') };
  if (segments.length === 2) return { ...base, kind: 'experiment' };
  if (segments.length === 4 && segments[2] === 'runs') return { ...base, kind: segments[3] === 'new' ? 'new' : 'run', runId: segments[3] };
  return { kind: 'missing' };
}
function pageHeading(title, description, crumbs = [], actions = []) {
  $('page-title').textContent = title; $('page-description').textContent = description;
  document.title = title + ' | Experiment Bench';
  $('breadcrumbs').replaceChildren(link('Experiments', '/experiments'));
  for (const [text, href] of crumbs) { $('breadcrumbs').append(node('span', '/')); $('breadcrumbs').append(href ? link(text, href) : node('span', text)); }
  $('page-actions').replaceChildren(...actions);
}
function refreshButton() {
  const button = node('button', 'Refresh', 'secondary'); button.id = 'refresh';
  button.onclick = async () => { button.disabled = true; try { await refresh(); tell('Up to date.'); } catch (error) { tell(error.message); } finally { button.disabled = false; } }; return button;
}
function navigate(href) {
  history.pushState(null, '', href); window.scrollTo(0, 0); void loadRoute(true);
}
document.addEventListener('click', event => {
  const anchor = event.target.closest('a[data-route]');
  if (!anchor || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || anchor.target || anchor.hasAttribute('download')) return;
  if (anchor.origin !== location.origin) return;
  event.preventDefault(); navigate(anchor.pathname + anchor.search);
});
window.addEventListener('popstate', () => { void loadRoute(true); });

function renderExperiments() {
  const container = $('experiments'); if (!container) return;
  const newest = new Map(); for (const d of experiments) if (!newest.has(d.stableId)) newest.set(d.stableId, d);
  patch(container, [experiments, runs], () => {
    const fragment = document.createDocumentFragment();
    for (const d of newest.values()) {
      const card = link(undefined, experimentPath(d), 'experiment-card');
      const latest = runs.find(r => r.stable_id === d.stableId);
      card.append(node('p', d.stableId, 'eyebrow'), node('h2', d.title), metadata(['Revision ' + d.revision, countLabel(d.units.length, 'unit'), countLabel(d.subjects.length, 'subject')]));
      const bottom = node('div', undefined, 'card-bottom'); bottom.append(latest ? badge(latest.status) : node('span', 'No runs yet', 'hint'), node('span', 'Open experiment >', 'card-action')); card.append(bottom); fragment.append(card);
    }
    if (!newest.size) fragment.append(node('p', 'No experiments yet. Published experiment definitions will appear here.', 'empty'));
    return fragment;
  });
}
function renderRuns() {
  const container = $('runs'); if (!container) return;
  const visible = runs.filter(r => r.stable_id === definition.stableId);
  patch(container, visible, () => {
    const fragment = document.createDocumentFragment();
    for (const r of visible) {
      const card = link(undefined, runPath(r), 'run-card');
      const title = node('div'); title.append(node('strong', (r.origin === 'gitops' ? 'Automatic' : 'Manual') + ' run'), node('span', 'Revision ' + r.revision + ' / ' + r.id.slice(0, 8), 'hint run-subtitle'));
      card.append(title, badge(r.status), node('span', new Date(r.created * 1000).toLocaleString(), 'hint run-time')); fragment.append(card);
    }
    if (!visible.length) fragment.append(node('p', 'No runs yet. Start a run to compare units for this experiment.', 'empty'));
    return fragment;
  });
}
function experimentPage(d) {
  pageHeading(d.title, 'Review the experiment and open a run to inspect its results.', [[d.title]], [refreshButton(), link('New run', newRunPath(d), 'button')]);
  const overview = node('section', undefined, 'surface'); overview.append(metadata(['Revision ' + d.revision, 'Enhancer ' + d.enhancerVersion, countLabel(d.subjects.length, 'subject'), countLabel(d.units.length, 'unit')]));
  const revisionLabel = node('label', 'Revision'); revisionLabel.htmlFor = 'revision'; const select = node('select'); select.id = 'revision';
  for (const version of experiments.filter(item => item.stableId === d.stableId)) { const option = node('option', 'Revision ' + version.revision); option.value = version.revision; select.append(option); }
  select.value = d.revision; select.onchange = () => navigate(experimentPath({ ...d, revision: select.value }));
  const revisionField = node('div', undefined, 'revision-field'); revisionField.append(revisionLabel, select); overview.append(revisionField);
  const grid = node('div', undefined, 'overview-grid'); const strategyBox = node('div'); strategyBox.append(node('h2', 'Units'));
  for (const unit of d.units) { const row = node('div', undefined, 'strategy-summary'); row.append(node('strong', unit.title), node('p', 'Strategy: ' + unit.strategy, 'hint')); strategyBox.append(row); }
  const prompts = node('div'); prompts.append(node('h2', 'Subjects'));
  for (const subject of d.subjects) prompts.append(disclosure(subject.id, node('p', subject.text, 'prompt')));
  grid.append(strategyBox, prompts); overview.append(grid, node('p', 'Evaluator profile: ' + d.evaluatorProfile.profile_id + ' / ' + d.evaluatorProfile.revision, 'hint'), evidence('Experiment definition', d, 'definition'));
  const heading = node('div', undefined, 'section-heading'); heading.append(node('h2', 'Runs'), node('span', 'Recent runs across revisions', 'hint'));
  const list = node('div'); list.id = 'runs'; $('page-content').replaceChildren(overview, heading, list); renderRuns();
}

function metricsTable(result) {
  const wrap = node('div', undefined, 'table-scroll'), table = node('table'), head = node('thead'), header = node('tr');
  for (const title of ['Evaluator / metric', 'Before', 'After', 'Delta']) header.append(node('th', title)); head.append(header); table.append(head);
  const body = node('tbody');
  const display = metric => !metric ? 'unknown' : metric.state !== 'known' && metric.value == null ? metric.state + (metric.reason ? ' (' + metric.reason + ')' : '') : typeof metric.value === 'number' ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 }).format(metric.value) : metric.label ?? 'unknown';
  for (const evaluator of result.before || []) for (const metric of evaluator.metrics || []) {
    const after = result.after?.find(x => x.evaluator_id === evaluator.evaluator_id)?.metrics.find(x => x.key === metric.key);
    const delta = result.deltas?.find(x => x.evaluator_id === evaluator.evaluator_id && x.metric_key === metric.key);
    const row = node('tr'); for (const value of [evaluator.evaluator_id + ' / ' + metric.key, display(metric), display(after), display(delta)]) row.append(node('td', String(value))); body.append(row);
  }
  table.append(body); wrap.append(table); return wrap;
}
function renderRun(r) {
  const container = $('run-detail'); if (!container || document.activeElement?.closest('#run-detail form')) return;
  patch(container, r, () => {
    const fragment = document.createDocumentFragment(), intro = node('section', undefined, 'surface');
    const actions = node('div', undefined, 'actions'); actions.append(badge(r.status), node('span', 'Assertions:', 'hint'), badge(r.assertion_outcome));
    if (['queued', 'running'].includes(r.status)) {
      const cancel = node('button', r.cancel_requested ? 'Cancellation requested' : 'Cancel run', 'danger'); cancel.disabled = Boolean(r.cancel_requested);
      cancel.onclick = async () => { cancel.disabled = true; try { await api('/api/runs/' + encodeURIComponent(r.id) + '/cancel', {}); await refresh(); } catch (error) { tell(error.message); cancel.disabled = false; } }; actions.append(cancel);
    } else if (terminal.has(r.status) && !r.cleanup_pending && !r.reconciliation_required) actions.append(link('Rerun with changes', newRunPath(definition, r.id), 'button'));
    intro.append(actions, metadata(['Run ' + r.id, 'Correlation ' + r.correlation_id, r.error_code, r.cleanup_pending ? 'Cleanup unconfirmed: execution slot held' : '']), evidence('Effective run settings', r.effective, 'effective'), evidence('Run history', r.events, 'events'));
    if (r.reconciliation_required) {
      const form = node('form'); form.append(node('p', 'Verify that the remote consumer has stopped before releasing the execution slot.', 'hint'));
      const label = node('label', 'Reconciliation evidence reference'); label.htmlFor = 'reconcile-reference'; const reference = node('input'); reference.id = 'reconcile-reference'; reference.required = true; reference.pattern = '[A-Za-z0-9][A-Za-z0-9._-]{0,95}';
      const confirm = node('button', 'Confirm remote stopped', 'secondary'); confirm.type = 'submit'; confirm.disabled = Boolean(r.cleanup_pending); form.append(label, reference, confirm);
      form.onsubmit = async event => { event.preventDefault(); confirm.disabled = true; try { await api('/api/runs/' + encodeURIComponent(r.id) + '/reconcile', { remoteStopped: true, evidenceReference: reference.value }); confirm.blur(); await refresh(); } catch (error) { tell(error.message); confirm.disabled = false; } }; intro.append(form);
    }
    fragment.append(intro);
    for (const attempt of r.attempts) {
      const panel = node('article', undefined, 'run-panel'), unit = r.effective.units.find(u => u.id === attempt.unit_id), subject = r.effective.subjects.find(s => s.id === attempt.subject_id);
      panel.dataset.attempt = attempt.id;
      const title = node('div', undefined, 'run-heading'); title.append(node('h2', 'Attempt: ' + unit.title + ' / ' + subject.id), badge(attempt.status));
      panel.append(title, metadata(['Strategy: ' + unit.strategy, attempt.progress ? 'Stage: ' + attempt.progress.stage : 'Not started']));
      const comparison = node('div', undefined, 'comparison');
      for (const [label, text, cls] of [['Original prompt', subject.text, 'prompt'], ['Enhanced prompt', attempt.result?.enhanced_prompt ?? 'No enhanced prompt available.', 'prompt candidate']]) { const column = node('div'); column.append(node('h3', label), node('div', text, cls)); comparison.append(column); }
      panel.append(comparison);
      if (attempt.result) panel.append(metricsTable(attempt.result), evidence('Complete result, provider provenance, timings and assertions', attempt.result, attempt.id));
      if (attempt.error_code) panel.append(node('p', attempt.error_code, 'hint')); fragment.append(panel);
    }
    return fragment;
  });
}

function newRunPage(d, source) {
  pageHeading(source ? 'Rerun experiment' : 'New run', d.title + ' / revision ' + d.revision + '. Adjust settings for this run.', [[d.title, experimentPath(d)], [source ? 'Rerun' : 'New run']]);
  const form = node('form'); form.id = 'run-form'; form.noValidate = true;
  const intro = node('section', undefined, 'surface'); intro.append(node('h2', 'Run configuration'), node('p', source ? 'Prefilled from run ' + source.id.slice(0, 8) + '. The original result stays unchanged.' : 'Start from the experiment defaults. Each selected unit has its own settings.', 'hint'), metadata(['Enhancer ' + d.enhancerVersion, 'Evaluator profile: ' + d.evaluatorProfile.profile_id + ' / ' + d.evaluatorProfile.revision]));
  const subjects = node('fieldset', undefined, 'field-group'); subjects.append(node('legend', 'Subjects'));
  const subjectInputs = d.subjects.map(subject => {
    const label = node('label', undefined, 'check-option'), input = node('input'); input.type = 'checkbox'; input.checked = !source || source.effective.subjects.some(s => s.id === subject.id);
    label.append(input, node('span', subject.id)); subjects.append(label); return [subject.id, input];
  }); intro.append(subjects); form.append(intro, node('h2', 'Units'));
  const editors = d.units.map(unit => {
    const saved = source?.effective.units.find(u => u.id === unit.id);
    const settings = saved || { parameters: { ...d.baseParameters, ...unit.parameters }, objective: { ...d.objective, ...unit.objective }, steering: { ...d.baseSteering, ...unit.steering }, consumerBinding: { ...d.consumerBinding, ...unit.consumerBinding } };
    const card = node('section', undefined, 'surface strategy-editor'); card.dataset.unit = unit.id;
    const title = node('label', undefined, 'check-option strategy-toggle'), enabled = node('input'); enabled.type = 'checkbox'; enabled.checked = !source || Boolean(saved);
    title.append(enabled, node('span', unit.title)); card.append(title, node('p', 'Strategy: ' + unit.strategy, 'hint'));
    const fields = node('fieldset', undefined, 'strategy-fields'); fields.disabled = !enabled.checked; fields.hidden = !enabled.checked;
    enabled.onchange = () => { fields.disabled = !enabled.checked; fields.hidden = !enabled.checked; };
    const parameters = schemaField(d.parameterSchema, settings.parameters, { id: unit.id + '-parameters', label: 'Parameters' });
    const objective = schemaField(runSchema.properties.objective, settings.objective, { id: unit.id + '-objective', label: 'Objective', definitions: runSchema.$defs });
    const steering = schemaField(runSchema.properties.steering, settings.steering, { id: unit.id + '-steering', label: 'Steering', definitions: runSchema.$defs });
    fields.append(parameters.element, disclosure('Objective and targets', objective.element), disclosure('Style and steering', steering.element));
    let consumer;
    if (unit.strategy.startsWith('consumer.')) {
      consumer = schemaField({ $ref: '#/$defs/ConsumerBinding' }, settings.consumerBinding, { id: unit.id + '-consumer', label: 'Consumer model', definitions: runSchema.$defs });
      fields.append(consumer.element, node('p', 'Use an operator-configured model alias. The evaluator profile stays the same for every unit.', 'hint'));
    }
    card.append(fields); form.append(card); return { unit, enabled, parameters, objective, steering, consumer };
  });
  const actions = node('div', undefined, 'form-actions'); const submit = node('button', 'Start run'); submit.type = 'submit';
  actions.append(node('p', 'Settings are saved with this run. The experiment definition is unchanged.', 'hint'), link('Cancel', source ? runPath(source) : experimentPath(d), 'button secondary'), submit); form.append(actions);
  let pending;
  const epoch = routeEpoch;
  form.onsubmit = async event => {
    event.preventDefault(); if (submit.disabled || !validateForm(form)) return;
    const selected = editors.filter(editor => editor.enabled.checked), subjectIds = subjectInputs.filter(([, input]) => input.checked).map(([id]) => id);
    if (!selected.length || !subjectIds.length) { tell('Select at least one unit and one subject.'); return; }
    const overrides = { parameters: {}, unitParameters: {}, unitObjectives: {}, unitSteering: {}, unitConsumerBindings: {}, unitIds: selected.map(editor => editor.unit.id), subjectIds };
    for (const editor of selected) {
      const id = editor.unit.id; overrides.unitParameters[id] = editor.parameters.read(); overrides.unitObjectives[id] = editor.objective.read(); overrides.unitSteering[id] = editor.steering.read();
      if (editor.consumer) overrides.unitConsumerBindings[id] = editor.consumer.read();
    }
    const body = { stableId: d.stableId, revision: d.revision, overrides, ...(source ? { retryOf: source.id } : {}) }, signature = json(body);
    if (!pending || pending.signature !== signature) pending = { signature, requestId: crypto.randomUUID() };
    submit.disabled = true; tell('');
    try {
      const response = await api('/api/runs', { ...body, requestId: pending.requestId });
      if (epoch === routeEpoch) navigate(runPath({ stable_id: d.stableId, id: response.runId }));
    } catch (error) { if (epoch === routeEpoch) tell(error.message); }
    finally { submit.disabled = false; }
  };
  $('page-content').replaceChildren(form);
}

async function loadRoute(focus = false) {
  const epoch = ++routeEpoch; tell('');
  try {
    activeRoute = parseRoute();
    if (activeRoute.kind === 'missing') throw new Error('Page not found.');
    const route = activeRoute;
    $('page-content').replaceChildren(node('p', 'Loading...', 'empty'));
    const [a, b] = await Promise.all([api('/api/experiments'), api('/api/runs')]);
    if (epoch !== routeEpoch) return;
    experiments = a.experiments; runs = b.runs; connected = true; $('workspace').hidden = false;
    if (route.kind === 'list') {
      pageHeading('Experiments', 'Choose an experiment to review its runs or start a new run.', [], [refreshButton()]);
      const cards = node('div', undefined, 'experiment-grid'); cards.id = 'experiments'; $('page-content').replaceChildren(cards); renderExperiments();
    } else {
      let source;
      if (route.kind === 'run' || route.from) {
        source = await api('/api/runs/' + encodeURIComponent(route.kind === 'run' ? route.runId : route.from));
        if (epoch !== routeEpoch) return;
        if (source.stable_id !== route.id || (route.revision && source.revision !== route.revision)) throw new Error('This run does not belong to the selected experiment revision.');
      }
      definition = experiments.find(d => d.stableId === route.id && (!(source?.revision || route.revision) || d.revision === (source?.revision || route.revision)));
      if (!definition) throw new Error('Experiment revision not found.');
      if (route.kind === 'experiment') experimentPage(definition);
      if (route.kind === 'run') {
        pageHeading('Run ' + source.id.slice(0, 8), definition.title + ' / revision ' + source.revision, [[definition.title, experimentPath(definition)], ['Results']], [refreshButton()]);
        const detail = node('section'); detail.id = 'run-detail'; $('page-content').replaceChildren(detail); renderRun(source);
      }
      if (route.kind === 'new') {
        if (source && (!terminal.has(source.status) || source.cleanup_pending || source.reconciliation_required)) throw new Error('This run must finish and complete cleanup before it can be rerun.');
        runSchema ||= await api('/api/run-form-schema');
        if (epoch !== routeEpoch) return;
        newRunPage(definition, source);
      }
    }
    if (focus) $('page-title').focus({ preventScroll: true });
  } catch (error) {
    if (epoch !== routeEpoch) return;
    connected = false;
    $('workspace').hidden = false;
    pageHeading('Unable to open page', '', [], [link('Back to experiments', '/experiments', 'button secondary')]);
    $('page-content').replaceChildren(node('p', error.status === 401 || error.status === 403 ? 'Your session is unavailable. Reload the page to reconnect through Cloudflare Access.' : error.message, 'empty'));
  }
}
async function refresh() {
  if (!connected || activeRoute?.kind === 'new') return;
  const epoch = routeEpoch, route = activeRoute, version = ++refreshVersion;
  const [a, b, r] = await Promise.all([api('/api/experiments'), api('/api/runs'), route.kind === 'run' ? api('/api/runs/' + encodeURIComponent(route.runId)) : null]);
  if (epoch !== routeEpoch || version !== refreshVersion) return;
  experiments = a.experiments; runs = b.runs;
  if (route.kind === 'list') renderExperiments();
  if (route.kind === 'experiment') renderRuns();
  if (route.kind === 'run') renderRun(r);
}
setInterval(async () => {
  if (document.hidden || polling || !connected || activeRoute?.kind === 'new') return;
  polling = true;
  try { await refresh(); } catch (error) { tell(error.message); } finally { polling = false; }
}, 3000);
if (location.pathname === '/') history.replaceState(null, '', '/experiments');
void loadRoute();
