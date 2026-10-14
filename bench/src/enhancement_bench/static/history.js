import { node } from './forms.js';

const keys = ['status', 'experiment', 'revision', 'origin', 'model', 'fromDate', 'toDate'];
const statuses = ['queued', 'running', 'succeeded', 'failed', 'cancelled', 'interrupted', 'superseded'];
const number = value => value == null ? 'Unknown' : new Intl.NumberFormat().format(value);
export const readFilters = query => Object.fromEntries(keys.filter(key => query.get(key)).map(key => [key, query.get(key)]));
export const hasFilters = route => keys.some(key => route.filters[key] && (!route.id || !['experiment', 'revision'].includes(key)));

export function historyPath(route, { before = null, filters = route.filters, api = false, stats = route.kind === 'stats' } = {}) {
  const query = new URLSearchParams();
  for (const key of keys) if (filters[key] && (api || !route.id || key !== 'experiment')) query.set(key, filters[key]);
  if (api) { query.set('limit', '10'); query.set('summary', 'true'); }
  if (before && !stats) query.set('before', before);
  const listPath = route.id ? '/experiments/' + encodeURIComponent(route.id) : '/experiments';
  const path = api ? '/api/runs' : stats ? (route.id ? listPath + '/stats' : '/stats') : listPath;
  return path + (query.size ? '?' + query : '');
}

export function filterToolbar(route, experiments, models, onApply) {
  const title = route.kind === 'stats' ? 'Filter stats' : 'Filter runs';
  const form = node('form', undefined, 'surface history-filters'); form.setAttribute('aria-label', title);
  const heading = node('div', undefined, 'filter-heading'); heading.append(node('h3', title), node('span', 'Across the full run history', 'hint')); form.append(heading);
  const fields = node('div', undefined, 'filter-grid');
  const controls = {};
  const field = (key, title, control) => {
    const wrap = node('div'), label = node('label', title); control.id = 'filter-' + key; control.name = key; label.htmlFor = control.id;
    control.value = route.filters[key] || ''; controls[key] = control; wrap.append(label, control); fields.append(wrap); return control;
  };
  const select = (key, title, options, empty) => {
    const control = node('select');
    for (const [value, text] of [['', empty], ...options]) { const option = node('option', text); option.value = value; control.append(option); }
    if (route.filters[key] && !options.some(([value]) => value === route.filters[key])) { const option = node('option', route.filters[key]); option.value = route.filters[key]; control.append(option); }
    return field(key, title, control);
  };
  select('status', 'Execution status', statuses.map(status => [status, status[0].toUpperCase() + status.slice(1)]), 'All statuses');
  if (!route.id) {
    const definitions = new Map(); for (const d of experiments) if (!definitions.has(d.stableId)) definitions.set(d.stableId, d.title);
    select('experiment', 'Experiment', [...definitions], 'All experiments');
    select('revision', 'Revision', [...new Set(experiments.map(d => d.revision))].map(value => [value, value]), 'All revisions');
  }
  select('origin', 'Trigger', [['gitops', 'Automatic'], ['ui', 'Manual']], 'All triggers');
  const model = node('input'); model.type = 'text'; model.placeholder = 'Any model alias'; model.maxLength = 96; model.pattern = '[A-Za-z0-9][A-Za-z0-9._-]{0,95}'; model.setAttribute('list', 'history-models');
  field('model', 'Model alias', model);
  const suggestions = node('datalist'); suggestions.id = 'history-models';
  for (const alias of models || []) { const option = node('option'); option.value = alias; suggestions.append(option); }
  const from = node('input'); from.type = 'date'; field('fromDate', 'Created from (UTC)', from);
  const to = node('input'); to.type = 'date'; field('toDate', 'Created through (UTC)', to);
  const validateDates = () => to.setCustomValidity(from.value && to.value && from.value > to.value ? 'End date must be on or after the start date.' : '');
  from.oninput = validateDates; to.oninput = validateDates;
  const actions = node('div', undefined, 'filter-actions'), apply = node('button', 'Apply filters'); apply.type = 'submit';
  const reset = node('a', 'Reset filters', 'button secondary'); reset.dataset.route = ''; reset.href = historyPath(route, { filters: !route.id ? {} : { experiment: route.id, revision: route.filters.revision } });
  actions.append(node('p', 'Model alias matches generation or evaluation. Dates include the entire UTC day.', 'hint'), reset, apply);
  form.append(fields, suggestions, actions);
  form.onsubmit = event => {
    event.preventDefault(); validateDates(); if (!form.reportValidity()) return;
    const filters = { ...route.filters };
    for (const [key, control] of Object.entries(controls)) { if (control.value) filters[key] = control.value; else delete filters[key]; }
    onApply(historyPath(route, { filters }));
  };
  return form;
}

const svgNode = (tag, attributes) => {
  const element = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
  return element;
};

function activityBars(days) {
  const max = Math.max(1, ...days.map(day => day.count));
  const svg = svgNode('svg', { viewBox: '0 0 600 150', 'aria-hidden': 'true', focusable: 'false' });
  for (const y of [10, 70, 130]) svg.append(svgNode('line', { x1: 0, x2: 600, y1: y, y2: y, class: 'chart-gridline' }));
  for (const [i, day] of days.entries()) {
    const width = 600 / days.length, height = day.count / max * 120;
    const bar = svgNode('rect', { x: i * width + 2, y: 130 - height, width: Math.max(1, width - 4), height, rx: 2, class: 'activity-bar' });
    const title = svgNode('title', {}); title.textContent = day.day + ': ' + number(day.count) + ' runs'; bar.append(title); svg.append(bar);
  }
  return svg;
}

export function statsPreview(summary, route) {
  const section = node('section', undefined, 'surface stats-preview'); section.setAttribute('aria-label', 'Stats preview');
  const heading = node('div', undefined, 'preview-heading'), intro = node('div');
  intro.append(node('h2', 'Stats overview'), node('p', 'Current run filters, across all pages.', 'hint'));
  const all = node('a', 'View all stats', 'button secondary'); all.dataset.route = ''; all.href = historyPath(route, { stats: true }); heading.append(intro, all); section.append(heading);
  if (!summary) { section.append(node('p', 'Stats are currently unavailable.', 'hint')); return section; }
  const content = node('div', undefined, 'preview-content'), totals = node('div', undefined, 'preview-totals');
  for (const [label, value] of [['Matching runs', summary.total], ['Planned attempts', summary.plannedAttempts], ['Succeeded', summary.statuses?.find(row => row.status === 'succeeded')?.count], ['Failed', summary.statuses?.find(row => row.status === 'failed')?.count]]) {
    const stat = node('div'); stat.append(node('strong', number(value)), node('span', label)); totals.append(stat);
  }
  const activity = node('div', undefined, 'preview-activity'), days = summary.activity || [];
  activity.append(node('strong', 'Run activity'), activityBars(days), node('span', summary.activityFrom + ' to ' + summary.activityTo + ' (UTC)', 'hint'));
  activity.setAttribute('role', 'img'); activity.setAttribute('aria-label', 'Run activity: ' + days.reduce((sum, day) => sum + day.count, 0) + ' runs created from ' + summary.activityFrom + ' to ' + summary.activityTo + ', UTC.');
  content.append(totals, activity); section.append(content); return section;
}

export function historyCharts(summary, route) {
  const section = node('section', undefined, 'history-insights'); section.setAttribute('aria-label', 'Run history charts');
  if (!summary) { section.append(node('p', 'Run history charts are unavailable.', 'hint')); return section; }
  const totals = node('div', undefined, 'history-totals');
  for (const [label, value] of [['Matching runs', summary.total], ['Planned attempts', summary.plannedAttempts]]) {
    const stat = node('div'); stat.append(node('strong', number(value)), node('span', label)); totals.append(stat);
  }
  const scope = node('p', 'Totals and execution statuses cover all matching runs, including older pages. Planned attempts count each saved case and variant combination.', 'hint');
  section.append(totals, scope);
  const charts = node('div', undefined, 'history-chart-grid');
  const activity = node('article', undefined, 'surface activity-chart'); activity.append(node('h3', 'Runs created per day'));
  activity.append(node('p', summary.activityFrom + ' to ' + summary.activityTo + ' (UTC)', 'hint chart-window'));
  const days = summary.activity || [], svg = activityBars(days);
  const scale = node('div', undefined, 'chart-scale'); scale.append(node('span', '0 baseline'), node('span', 'Peak: ' + number(Math.max(0, ...days.map(day => day.count))) + ' runs / day'));
  activity.append(svg, scale);
  if (!days.some(day => day.count > 0)) activity.append(node('p', 'No runs created in this chart window.', 'hint'));
  const values = node('details'); values.dataset.key = 'daily-counts'; values.append(node('summary', 'Daily counts'));
  const table = node('table'), head = node('thead'), header = node('tr');
  for (const label of ['Date (UTC)', 'Runs created']) { const th = node('th', label); th.scope = 'col'; header.append(th); }
  head.append(header); table.append(head); const body = node('tbody');
  for (const day of days) { const row = node('tr'); row.append(node('td', day.day), node('td', number(day.count))); body.append(row); }
  table.append(body); const scroll = node('div', undefined, 'daily-counts'); scroll.append(table); values.append(scroll); activity.append(values);
  const status = node('article', undefined, 'surface status-chart'); status.append(node('h3', 'Execution status'), node('p', 'Select a status to filter the list. Execution success is separate from assertion results.', 'hint'));
  const list = node('div', undefined, 'status-bars');
  for (const entry of summary.statuses) {
    const selected = route.filters.status === entry.status;
    const anchor = node('a', undefined, 'status-bar'); anchor.dataset.route = ''; anchor.dataset.status = entry.status;
    anchor.href = historyPath(route, { filters: { ...route.filters, status: selected ? '' : entry.status } });
    if (selected) anchor.setAttribute('aria-current', 'true');
    anchor.setAttribute('aria-label', entry.status + ': ' + number(entry.count) + ' runs' + (selected ? ', clear status filter' : ', filter runs'));
    const track = node('span', undefined, 'status-track'), fill = node('span', undefined, 'status-fill'); fill.style.width = (summary.total ? entry.count / summary.total * 100 : 0) + '%'; track.append(fill);
    anchor.append(node('span', entry.status, 'status-name'), track, node('strong', number(entry.count))); list.append(anchor);
  }
  status.append(list); charts.append(activity, status); section.append(charts, comparisonCharts(summary.comparisons)); return section;
}

const metricNumber = value => value == null ? 'Unknown' : new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 }).format(value);
const modelLabel = row => row.strategy?.startsWith('script.') ? 'No model (script)' : row.model || 'Unknown model alias';
const generationLabel = row => [modelLabel(row), row.generation?.reported_model || row.generation?.model, row.generation?.model_revision].filter(Boolean).join(' / ');

function pairedBars(rows, domain) {
  const list = node('div', undefined, 'metric-bars');
  const values = domain || rows.flatMap(row => [row.before, row.after]).filter(value => value != null);
  const extent = Math.max(1, ...values.map(Math.abs));
  const low = Math.min(0, ...values) / extent, high = Math.max(0, ...values) / extent, span = high - low || 1;
  for (const row of rows) {
    const item = node('div', undefined, 'metric-row'); item.append(node('strong', row.label), node('span', row.count + ' paired observations' + (row.excluded ? ' / ' + row.excluded + ' unavailable or non-comparable' : ''), 'hint'));
    for (const side of ['before', 'after']) {
      const line = node('div', undefined, 'metric-bar-line'), track = node('span', undefined, 'metric-track'), fill = node('span', undefined, 'metric-fill ' + side);
      track.setAttribute('aria-hidden', 'true');
      if (row[side] != null) { fill.style.left = ((Math.min(0, row[side] / extent) - low) / span * 100) + '%'; fill.style.width = (Math.abs(row[side] / extent) / span * 100) + '%'; }
      const zero = node('span', undefined, 'metric-zero'); zero.style.left = (-low / span * 100) + '%'; track.append(fill, zero);
      line.append(node('span', side === 'before' ? 'Before' : 'After'), track, node('strong', metricNumber(row[side]))); item.append(line);
    }
    item.append(node('span', 'Mean paired delta: ' + metricNumber(row.delta), 'hint')); list.append(item);
  }
  return list;
}

function combine(rows, label) {
  const count = rows.reduce((sum, row) => sum + row.count, 0), result = { label, count, excluded: rows.reduce((sum, row) => sum + row.excluded, 0) };
  for (const key of ['before', 'after', 'delta']) result[key] = count ? rows.reduce((sum, row) => sum + (row.count ? row[key] * (row.count / count) : 0), 0) : null;
  return result;
}

function comparisonCharts(comparisons) {
  const section = node('section', undefined, 'surface metric-comparisons'); section.setAttribute('aria-label', 'Metric comparisons');
  section.append(node('h3', 'Before / After comparisons'), node('p', 'Paired numeric results, kept separate by experiment revision, evaluator provenance and metric. Each observation is one attempt with comparable before and after values. Missing, categorical and non-comparable values are excluded; attempts without results do not contribute.', 'hint'));
  const groups = comparisons?.groups || [];
  if (!groups.length) { section.append(node('p', 'No recorded metrics for these filters yet.', 'empty')); return section; }
  if (comparisons.truncated) section.append(node('p', 'Showing up to ' + comparisons.groupLimit + ' metric groups from the newest results. Narrow the filters to compare the remaining groups.', 'hint'));
  const scopes = new Map(groups.map(row => [row.scopeKey, row]));
  const label = node('label', 'Metric and evaluation scope'); label.htmlFor = 'comparison-scope';
  const select = node('select'); select.id = 'comparison-scope'; select.dataset.preserve = 'comparison-scope';
  for (const [key, row] of scopes) {
    const title = [row.metric, row.experiment + ' r' + row.revision, row.evaluator, row.provenance?.metric_version || 'unknown metric version', key.slice(0, 6)].join(' / ');
    const option = node('option', title); option.value = key; select.append(option);
  }
  const content = node('div');
  const render = () => {
    const rows = groups.filter(row => row.scopeKey === select.value), scope = scopes.get(select.value); if (!scope) return;
    const domain = rows.flatMap(row => [row.before, row.after]).filter(value => value != null);
    const scale = node('p', domain.length ? 'Shared chart scale: ' + metricNumber(Math.min(0, ...domain)) + ' to ' + metricNumber(Math.max(0, ...domain)) : 'No comparable numeric pairs for this metric.', 'hint');
    const overall = node('article', undefined, 'comparison-overall'); overall.append(node('h4', 'Before / After mean'), pairedBars([combine(rows, scope.metric)], domain));
    const variants = node('article'); variants.append(node('h4', 'By variant and model'), pairedBars(rows.map(row => ({ ...row, label: row.variant + ' / ' + generationLabel(row) })), domain));
    const models = new Map();
    for (const row of rows) { const key = JSON.stringify([row.model, row.generation, row.strategy?.startsWith('script.')]); if (!models.has(key)) models.set(key, []); models.get(key).push(row); }
    const modelChart = node('article'); modelChart.append(node('h4', 'By generation model'), pairedBars([...models.values()].map(rows => combine(rows, generationLabel(rows[0]))), domain));
    const grid = node('div', undefined, 'metric-comparison-grid'); grid.append(variants, modelChart);
    const provenance = node('details'); provenance.dataset.key = 'comparison-provenance'; provenance.append(node('summary', 'Evaluation identity'), node('pre', JSON.stringify({ coreVersion: scope.coreVersion, evaluator: scope.evaluator, kind: scope.kind, ...scope.provenance }, null, 2)));
    content.replaceChildren(scale, overall, grid, node('p', 'Descriptive averages across the selected runs. Models and variants may have different cases and sample sizes; a larger value is not necessarily better. Use the same cases for a controlled comparison.', 'hint'), provenance);
  };
  select.onchange = render; section.append(label, select, content); render(); return section;
}
