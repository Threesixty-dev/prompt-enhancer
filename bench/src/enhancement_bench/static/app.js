import { node, schemaField, validateForm } from './forms.js';
import { evaluatorEditor, evaluatorErrors } from './evaluators.js';
import { attemptAnchor, countLabel, generationLabel, modelEvidence, modelSummary, variationOverview, variantDescription } from './overview.js';
import { filterToolbar, hasFilters, historyCharts, historyPath, readFilters, statsPreview } from './history.js';

const $ = id => document.getElementById(id);
const json = value => JSON.stringify(value, null, 2);
const badge = value => node('span', value || 'unknown', 'badge ' + (value || 'unknown'));
const tell = message => { $('notice').textContent = message; };
const terminal = new Set(['succeeded', 'failed', 'cancelled', 'interrupted', 'superseded']);
let connected = false, experiments = [], runs = [], routeEpoch = 0;
let activeRoute, definition, runSchema, runPage, polling = false, refreshVersion = 0;
const snapshots = new WeakMap();

async function api(path, body) {
  const headers = { 'Content-Type': 'application/json' };
  const response = await fetch(path, { method: body === undefined ? 'GET' : 'POST', cache: 'no-store', credentials: 'same-origin', headers, body: body === undefined ? undefined : json(body) });
  if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Bench unavailable. Reload the page to reconnect.');
  const value = await response.json();
  if (!response.ok) { const code = value.error?.code; const error = new Error(evaluatorErrors[code] || code || 'request_failed'); error.status = response.status; throw error; }
  return value;
}

function link(text, href, className) {
  const anchor = node('a', text, className); anchor.href = href; anchor.dataset.route = ''; return anchor;
}
const experimentPath = d => '/experiments/' + encodeURIComponent(d.stableId) + '?revision=' + encodeURIComponent(d.revision);
const newRunPath = (d, from) => '/experiments/' + encodeURIComponent(d.stableId) + '/runs/new?revision=' + encodeURIComponent(d.revision) + (from ? '&from=' + encodeURIComponent(from) : '');
const runPath = r => '/experiments/' + encodeURIComponent(r.stable_id) + '/runs/' + encodeURIComponent(r.id);
function labeledValue(label, value, tag = 'span', className) {
  const element = node(tag, undefined, className);
  element.append(node('strong', label + ': ', 'meta-label'), node('span', String(value)));
  return element;
}
function metadata(values) {
  const element = node('div', undefined, 'meta');
  for (const value of values.filter(Boolean)) element.append(Array.isArray(value) ? labeledValue(...value) : node('span', value));
  return element;
}
function disclosure(title, content, key) {
  const element = node('details'); if (key) element.dataset.key = key;
  element.append(node('summary', title), content); return element;
}
const evidence = (title, value, key) => disclosure(title, node('pre', json(value)), key);
function patch(container, value, build) {
  const signature = json(value);
  if (snapshots.get(container) === signature) return;
  const open = new Set([...container.querySelectorAll('details[open][data-key]')].map(d => d.dataset.key));
  const choices = [...container.querySelectorAll('select[data-preserve]')].map(control => [control.dataset.preserve, control.value]);
  container.replaceChildren(build());
  for (const [key, value] of choices) {
    const control = container.querySelector('select[data-preserve="' + key + '"]');
    if (control && [...control.options].some(option => option.value === value)) { control.value = value; control.dispatchEvent(new Event('change')); }
  }
  for (const item of container.querySelectorAll('details[data-key]')) item.open = open.has(item.dataset.key);
  snapshots.set(container, signature);
}
function parseRoute() {
  const segments = location.pathname.split('/').filter(Boolean).map(decodeURIComponent), query = new URLSearchParams(location.search);
  const history = { before: query.get('before'), filters: readFilters(query) };
  if (!segments.length || (segments.length === 1 && segments[0] === 'experiments')) return { kind: 'list', ...history };
  if (segments.length === 1 && segments[0] === 'stats') return { kind: 'stats', ...history };
  if (segments[0] !== 'experiments' || !/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$/.test(segments[1] || '')) return { kind: 'missing' };
  const base = { id: segments[1], revision: query.get('revision'), from: query.get('from') };
  if (segments.length === 2) return { ...base, ...history, kind: 'experiment' };
  if (segments.length === 3 && segments[2] === 'stats') return { ...base, ...history, kind: 'stats' };
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
      const latest = runs.find(r => r.stable_id === d.stableId && r.revision === d.revision);
      card.append(node('p', d.stableId, 'eyebrow'), node('h3', d.title), metadata([['Revision', d.revision], countLabel(d)]), modelSummary(d));
      const bottom = node('div', undefined, 'card-bottom'); bottom.append(latest ? badge(latest.status) : node('span', 'No runs yet', 'hint'), node('span', 'Open experiment >', 'card-action')); card.append(bottom); fragment.append(card);
    }
    if (!newest.size) fragment.append(node('p', 'No experiments yet. Published experiment definitions will appear here.', 'empty'));
    return fragment;
  });
}
function historyFrame() {
  const preview = node('div'); preview.id = 'stats-preview';
  const pagination = node('nav', undefined, 'run-pagination'); pagination.id = 'run-pagination'; pagination.setAttribute('aria-label', 'Run history');
  return { filters: filterToolbar(activeRoute, experiments, runPage.modelOptions, navigate), preview, pagination };
}
function renderHistory() {
  const global = activeRoute.kind === 'list', container = $(global ? 'all-runs' : 'runs'); if (!container) return;
  patch(container, [runPage.runs, experiments], () => {
    const fragment = document.createDocumentFragment();
    for (const r of runPage.runs) {
      const d = experiments.find(item => item.stableId === r.stable_id && item.revision === r.revision);
      const card = link(undefined, runPath(r), 'run-card');
      const title = node('div');
      title.append(node('strong', global ? d?.title || r.stable_id : (r.origin === 'gitops' ? 'Automatic' : 'Manual') + ' run'), metadata([
        ['Experiment', r.stable_id], ['Revision', r.revision], ['Run', r.id.slice(0, 8)],
        (r.origin === 'gitops' ? 'Automatic' : 'Manual') + ' run',
      ]));
      title.append(node('p', countLabel(r.configuration || {}), 'hint run-subtitle'), modelSummary(r.configuration));
      card.append(title, badge(r.status), labeledValue('Created', new Date(r.created * 1000).toLocaleString(), 'span', 'hint run-time'));
      fragment.append(card);
    }
    if (!runPage.runs.length) fragment.append(node('p', hasFilters(activeRoute) ? 'No runs match these filters. Adjust or reset the filters to see more runs.' : activeRoute.before ? 'No older runs on this page. Return to the newest runs.' : global ? 'No runs yet. Choose an experiment below to start a run.' : 'No runs yet for this revision. Start a run to compare its units.', 'empty'));
    return fragment;
  });
  patch($('run-pagination'), [activeRoute.before, runPage.nextCursor], () => {
    const fragment = document.createDocumentFragment();
    if (activeRoute.before) fragment.append(link('Newest runs', historyPath(activeRoute), 'button secondary'));
    if (runPage.nextCursor) fragment.append(link('Older runs', historyPath(activeRoute, { before: runPage.nextCursor }), 'button secondary'));
    return fragment;
  });
  patch($('stats-preview'), runPage.summary, () => statsPreview(runPage.summary, activeRoute));
}
function renderStats() {
  const container = $('history-charts'); if (container) patch(container, runPage.summary, () => historyCharts(runPage.summary, activeRoute));
}
function statsPage(d) {
  const back = historyPath(activeRoute, { stats: false });
  pageHeading('Run stats', d ? d.title + ' / revision ' + d.revision : 'Explore activity, execution status and metric comparisons across runs.', d ? [[d.title, back], ['Stats']] : [['Stats']], [refreshButton(), link('Back to runs', back, 'button secondary')]);
  const charts = node('div'); charts.id = 'history-charts';
  $('page-content').replaceChildren(filterToolbar(activeRoute, experiments, runPage.modelOptions, navigate), charts); renderStats();
}
function experimentPage(d) {
  pageHeading(d.title, 'Review the experiment and open a run to inspect its results.', [[d.title]], [refreshButton(), link('New run', newRunPath(d), 'button')]);
  const overview = node('section', undefined, 'surface'); overview.append(metadata([['Revision', d.revision], ['Enhancer version', d.enhancerVersion]]), modelSummary(d), node('p', 'Model aliases are configured selections. Reported model identities appear in each attempt after execution.', 'hint'));
  const revisionLabel = node('label', 'Revision'); revisionLabel.htmlFor = 'revision'; const select = node('select'); select.id = 'revision';
  for (const version of experiments.filter(item => item.stableId === d.stableId)) { const option = node('option', 'Revision ' + version.revision); option.value = version.revision; select.append(option); }
  select.value = d.revision; select.onchange = () => navigate(historyPath(activeRoute, { filters: { ...activeRoute.filters, revision: select.value } }));
  const revisionField = node('div', undefined, 'revision-field'); revisionField.append(revisionLabel, select); overview.append(revisionField);
  const grid = node('div', undefined, 'overview-grid'); const strategyBox = node('div'); strategyBox.append(node('h2', 'Variants (units)'));
  for (const unit of d.units) { const row = node('div', undefined, 'strategy-summary'); row.append(node('strong', unit.title), labeledValue('Strategy', unit.strategy, 'p', 'hint'), labeledValue('Generation model alias', generationLabel(d, unit), 'p', 'hint'), node('p', variantDescription(d, unit), 'hint')); strategyBox.append(row); }
  const prompts = node('div'); prompts.append(node('h2', 'Input cases (subjects)'));
  for (const subject of d.subjects) prompts.append(disclosure(subject.id, node('p', subject.text, 'prompt')));
  grid.append(strategyBox, prompts); overview.append(grid, labeledValue('Evaluator profile', d.evaluatorProfile.profile_id + ' / ' + d.evaluatorProfile.revision, 'p', 'hint'), evidence('Experiment definition', d, 'definition'));
  const heading = node('div', undefined, 'section-heading'); heading.append(node('h2', 'Runs'), node('span', 'Runs for revision ' + d.revision, 'hint'));
  const list = node('div'); list.id = 'runs'; const history = historyFrame();
  $('page-content').replaceChildren(variationOverview(d), overview, heading, history.preview, history.filters, list, history.pagination); renderHistory();
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
  table.append(body); wrap.append(table);
  if ((result.before || []).some(evaluator => evaluator.kind === 'deterministic')) {
    wrap.append(node('p', 'Rule-based scores measure detected text cues, not a model’s judgment. Zero is a measured score; unknown means there was no eligible observation. A delta stays unknown when either side is unknown.', 'hint'));
  }
  if ((result.before || []).some(evaluator => evaluator.metrics.some(metric => metric.reason === 'diagnostic_task_not_detected'))) {
    wrap.append(node('p', 'Problem evidence applies to debugging or diagnostic requests. No diagnostic task was detected in this prompt.', 'hint'));
  }
  return wrap;
}
function renderRun(r) {
  const container = $('run-detail'); if (!container || document.activeElement?.closest('#run-detail form')) return;
  patch(container, r, () => {
    const fragment = document.createDocumentFragment(), intro = node('section', undefined, 'surface');
    const actions = node('div', undefined, 'actions'); actions.append(badge(r.status), node('strong', 'Assertions:', 'hint meta-label'), badge(r.assertion_outcome));
    if (['queued', 'running'].includes(r.status)) {
      const cancel = node('button', r.cancel_requested ? 'Cancellation requested' : 'Cancel run', 'danger'); cancel.disabled = Boolean(r.cancel_requested);
      cancel.onclick = async () => { cancel.disabled = true; try { await api('/api/runs/' + encodeURIComponent(r.id) + '/cancel', {}); await refresh(); } catch (error) { tell(error.message); cancel.disabled = false; } }; actions.append(cancel);
    } else if (terminal.has(r.status) && !r.cleanup_pending && !r.reconciliation_required) actions.append(link('Rerun with changes', newRunPath(definition, r.id), 'button'));
    intro.append(actions, metadata([['Run', r.id], ['Enhancer version', r.effective.enhancerVersion], ['Correlation', r.correlation_id], r.error_code ? ['Error', r.error_code] : null, r.cleanup_pending ? ['Cleanup', 'Unconfirmed: execution slot held'] : null]), modelSummary(r.effective), evidence('Effective run settings', r.effective, 'effective'), evidence('Run history', r.events, 'events'));
    if (r.reconciliation_required) {
      const form = node('form'); form.append(node('p', 'Verify that the remote consumer has stopped before releasing the execution slot.', 'hint'));
      const label = node('label', 'Reconciliation evidence reference'); label.htmlFor = 'reconcile-reference'; const reference = node('input'); reference.id = 'reconcile-reference'; reference.required = true; reference.pattern = '[A-Za-z0-9][A-Za-z0-9._-]{0,95}';
      const confirm = node('button', 'Confirm remote stopped', 'secondary'); confirm.type = 'submit'; confirm.disabled = Boolean(r.cleanup_pending); form.append(label, reference, confirm);
      form.onsubmit = async event => { event.preventDefault(); confirm.disabled = true; try { await api('/api/runs/' + encodeURIComponent(r.id) + '/reconcile', { remoteStopped: true, evidenceReference: reference.value }); confirm.blur(); await refresh(); } catch (error) { tell(error.message); confirm.disabled = false; } }; intro.append(form);
    }
    fragment.append(intro, variationOverview(r.effective, { attempts: r.attempts, onAttempt: attempt => {
      const target = document.getElementById(attemptAnchor(attempt.id)); target?.scrollIntoView({ block: 'start' }); target?.focus({ preventScroll: true });
    } }));
    for (const [index, attempt] of r.attempts.entries()) {
      const panel = node('article', undefined, 'run-panel'), unit = r.effective.units.find(u => u.id === attempt.unit_id), subject = r.effective.subjects.find(s => s.id === attempt.subject_id);
      panel.dataset.attempt = attempt.id; panel.id = attemptAnchor(attempt.id); panel.tabIndex = -1;
      const title = node('div', undefined, 'run-heading'); title.append(node('h2', 'Attempt ' + ((attempt.position ?? index) + 1) + ': ' + unit.title + ' / ' + subject.id), badge(attempt.status));
      panel.append(title, metadata([['Strategy', unit.strategy], ['Generation model alias', generationLabel(r.effective, unit)], ['Stage', attempt.progress ? attempt.progress.stage : 'Not started']]));
      const comparison = node('div', undefined, 'comparison');
      for (const [label, text, cls] of [['Original prompt', subject.text, 'prompt'], ['Enhanced prompt', attempt.result?.enhanced_prompt ?? 'No enhanced prompt available.', 'prompt candidate']]) { const column = node('div'); column.append(node('h3', label), node('div', text, cls)); comparison.append(column); }
      panel.append(comparison);
      if (attempt.result) panel.append(modelEvidence(attempt.result), metricsTable(attempt.result), evidence('Complete result, provider provenance, timings and assertions', attempt.result, attempt.id));
      else panel.append(node('p', 'Reported model: unknown. No result provenance is available yet.', 'hint'));
      if (attempt.error_code) panel.append(node('p', attempt.error_code, 'hint')); fragment.append(panel);
    }
    return fragment;
  });
}

function newRunPage(d, source) {
  pageHeading(source ? 'Rerun experiment' : 'New run', d.title + ' / revision ' + d.revision + '. Adjust settings for this run.', [[d.title, experimentPath(d)], [source ? 'Rerun' : 'New run']]);
  const form = node('form'); form.id = 'run-form'; form.noValidate = true;
  const profile = source?.effective.evaluatorProfile || d.evaluatorProfile;
  const evaluation = evaluatorEditor(profile, runSchema, experiments);
  const intro = node('section', undefined, 'surface'); intro.append(node('h2', 'Run configuration'), node('p', source ? 'Prefilled from run ' + source.id.slice(0, 8) + '. The original result stays unchanged.' : 'Start from the experiment defaults. Each selected unit has its own settings.', 'hint'), metadata([['Enhancer version', d.enhancerVersion], ['Starting evaluator profile', profile.profile_id + ' / ' + profile.revision]]));
  const subjects = node('fieldset', undefined, 'field-group'); subjects.append(node('legend', 'Input cases (subjects)'));
  const subjectInputs = d.subjects.map(subject => {
    const label = node('label', undefined, 'check-option'), input = node('input'); input.type = 'checkbox'; input.checked = !source || source.effective.subjects.some(s => s.id === subject.id);
    label.append(input, node('span', subject.id)); subjects.append(label); return [subject.id, input];
  }); intro.append(subjects); const preview = node('div'); preview.id = 'run-preview'; form.append(intro, evaluation.element, preview, node('h2', 'Variants (units)'));
  const editors = d.units.map(unit => {
    const saved = source?.effective.units.find(u => u.id === unit.id);
    const settings = saved || { parameters: { ...d.baseParameters, ...unit.parameters }, objective: { ...d.objective, ...unit.objective }, steering: { ...d.baseSteering, ...unit.steering }, consumerBinding: { ...d.consumerBinding, ...unit.consumerBinding } };
    const card = node('section', undefined, 'surface strategy-editor'); card.dataset.unit = unit.id;
    const title = node('label', undefined, 'check-option strategy-toggle'), enabled = node('input'); enabled.type = 'checkbox'; enabled.checked = !source || Boolean(saved);
    title.append(enabled, node('span', unit.title)); card.append(title, labeledValue('Strategy', unit.strategy, 'p', 'hint'));
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
  const updatePreview = () => {
    const selected = { ...d, evaluatorProfile: { ...profile, evaluators: evaluation.read() }, subjects: d.subjects.filter(subject => subjectInputs.some(([id, input]) => id === subject.id && input.checked)),
      units: editors.filter(editor => editor.enabled.checked).map(editor => ({ ...editor.unit, steering: editor.steering.read(), consumerBinding: editor.consumer?.read() })) };
    patch(preview, selected, () => { const content = document.createDocumentFragment(); content.append(variationOverview(selected), modelSummary(selected)); return content; });
  };
  form.addEventListener('input', updatePreview); form.addEventListener('change', updatePreview); updatePreview();
  let pending;
  const epoch = routeEpoch;
  form.onsubmit = async event => {
    event.preventDefault(); if (submit.disabled || !validateForm(form)) return;
    const selected = editors.filter(editor => editor.enabled.checked), subjectIds = subjectInputs.filter(([, input]) => input.checked).map(([id]) => id);
    if (!selected.length || !subjectIds.length) { tell('Select at least one unit and one subject.'); return; }
    const overrides = { parameters: {}, unitParameters: {}, unitObjectives: {}, unitSteering: {}, unitConsumerBindings: {}, unitIds: selected.map(editor => editor.unit.id), subjectIds };
    const evaluators = evaluation.read();
    if (json(evaluators) !== json(d.evaluatorProfile.evaluators)) overrides.evaluators = evaluators;
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
  const epoch = ++routeEpoch; connected = false; tell('');
  try {
    activeRoute = parseRoute();
    if (activeRoute.kind === 'missing') throw new Error('Page not found.');
    const route = activeRoute;
    $('page-content').replaceChildren(node('p', 'Loading...', 'empty'));
    const globalHistory = !route.id && ['list', 'stats'].includes(route.kind);
    const [a, b, page] = await Promise.all([api('/api/experiments'), route.kind === 'list' ? api('/api/runs') : null, globalHistory ? api(historyPath(route, { api: true, before: route.before })) : null]);
    if (epoch !== routeEpoch) return;
    experiments = a.experiments; runs = b?.runs || []; $('workspace').hidden = false;
    if (route.kind === 'list') {
      pageHeading('All runs', 'Runs across all experiments and revisions, newest first.', [], [refreshButton()]);
      runPage = page;
      const runList = node('section'); runList.id = 'all-runs'; runList.setAttribute('aria-labelledby', 'page-title');
      const history = historyFrame();
      const heading = node('div', undefined, 'section-heading'); heading.append(node('h2', 'Experiments'));
      const description = node('p', 'Choose an experiment to review its revisions or start a new run.', 'hint');
      const cards = node('div', undefined, 'experiment-grid'); cards.id = 'experiments';
      $('page-content').replaceChildren(history.preview, history.filters, runList, history.pagination, heading, description, cards); renderHistory(); renderExperiments();
    } else if (globalHistory && route.kind === 'stats') {
      runPage = page; statsPage();
    } else {
      let source;
      if (route.kind === 'run' || route.from) {
        source = await api('/api/runs/' + encodeURIComponent(route.kind === 'run' ? route.runId : route.from));
        if (epoch !== routeEpoch) return;
        if (source.stable_id !== route.id || (route.revision && source.revision !== route.revision)) throw new Error('This run does not belong to the selected experiment revision.');
      }
      definition = experiments.find(d => d.stableId === route.id && (!(source?.revision || route.revision) || d.revision === (source?.revision || route.revision)));
      if (!definition) throw new Error('Experiment revision not found.');
      if (['experiment', 'stats'].includes(route.kind)) {
        route.filters = { ...route.filters, experiment: definition.stableId, revision: definition.revision };
        const page = await api(historyPath(route, { api: true, before: route.before }));
        if (epoch !== routeEpoch) return;
        runPage = page; if (route.kind === 'stats') statsPage(definition); else experimentPage(definition);
      }
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
    connected = true;
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
  const [a, b, r, page] = await Promise.all([api('/api/experiments'), route.kind === 'list' ? api('/api/runs') : null, route.kind === 'run' ? api('/api/runs/' + encodeURIComponent(route.runId)) : null, ['list', 'experiment', 'stats'].includes(route.kind) ? api(historyPath(route, { api: true, before: route.before })) : null]);
  if (epoch !== routeEpoch || version !== refreshVersion) return;
  experiments = a.experiments; runs = b?.runs || [];
  if (page) { runPage = page; if (route.kind === 'stats') renderStats(); else renderHistory(); }
  if (route.kind === 'list') renderExperiments();
  if (route.kind === 'run') renderRun(r);
}
setInterval(async () => {
  if (document.hidden || polling || !connected || activeRoute?.kind === 'new') return;
  polling = true;
  try { await refresh(); } catch (error) { tell(error.message); } finally { polling = false; }
}, 3000);
if (location.pathname === '/') history.replaceState(null, '', '/experiments');
void loadRoute();
