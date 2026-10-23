import { node } from './forms.js';

const labels = { known: 'Known', unknown: 'Unknown', abstained: 'Abstained', not_applicable: 'Not applicable', execution_error: 'Evaluation error', missing: 'Not recorded' };
const reasons = {
  diagnostic_task_not_detected: 'no diagnostic task detected',
  constraints_unobserved: 'no constraint clause detected',
  deliverables_unobserved: 'no deliverable clause detected',
  requirements_unknown: 'no requirement clause detected',
  unsupported_language: 'language unsupported or text too short to classify',
  source_extraction_incomplete: 'source text could not be analysed completely',
  rubric_abstained: 'rubric evaluator declined to classify',
  rubric_reply_invalid: 'rubric reply was invalid or incomplete',
  evaluator_failed: 'evaluator request failed',
  workflow_no_candidate: 'workflow produced no candidate',
  provenance_mismatch: 'evaluator identities or versions differ',
};
const number = value => new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 }).format(value);
const stateLabel = metric => labels[metric?.state] || metric?.state || labels.missing;
const reason = metric => reasons[metric?.reason] || metric?.reason?.replaceAll('_', ' ');

export function measurementText(metric) {
  if (!metric) return labels.missing;
  if (metric.state === 'known') return typeof metric.value === 'number' ? number(metric.value) : metric.label ?? labels.missing;
  return stateLabel(metric) + (reason(metric) ? ': ' + reason(metric) : '');
}

export function deltaText(delta, before, after) {
  if (!delta) return labels.missing;
  if (delta.state === 'comparable' && typeof delta.value === 'number') return number(delta.value);
  if (delta.reason === 'categorical_metric' && before?.state === 'known' && after?.state === 'known') {
    return `${measurementText(before)} \u2192 ${measurementText(after)} (categorical)`;
  }
  if (delta.reason === 'metric_unknown') return `No numeric delta: before ${stateLabel(before).toLowerCase()}, after ${stateLabel(after).toLowerCase()}`;
  return 'No numeric delta: ' + (reason(delta) || delta.state.replaceAll('_', ' '));
}

function rowsFor(result) {
  const rows = new Map();
  for (const side of ['before', 'after']) for (const evaluator of result[side] || []) for (const metric of evaluator.metrics || []) {
    const key = evaluator.evaluator_id + '/' + metric.key;
    if (!rows.has(key)) rows.set(key, { evaluator: evaluator.evaluator_id, key: metric.key });
    rows.get(key)[side] = metric;
  }
  return [...rows.values()];
}

export function metricsTable(result) {
  const section = node('section', undefined, 'metric-readings');
  section.setAttribute('aria-label', 'Evaluator measurements');
  const rows = rowsFor(result), counts = {};
  for (const row of rows) for (const side of ['before', 'after']) {
    const state = row[side]?.state || 'missing'; counts[state] = (counts[state] || 0) + 1;
  }
  section.append(node('h3', 'Evaluator coverage'), node('p', rows.length
    ? 'Before and after: ' + Object.entries(labels).filter(([key]) => counts[key]).map(([key, label]) => `${counts[key]} ${label.toLowerCase()}`).join(' \u00b7 ')
    : 'No evaluator readings recorded.', 'measurement-coverage'));
  section.append(node('p', 'Unknown, abstained, and not applicable readings have no numeric score. Categorical results show label transitions. Execution status and assertion outcomes are reported separately.', 'hint'));
  const wrap = node('div', undefined, 'table-scroll'), table = node('table'), head = node('thead'), header = node('tr');
  for (const title of ['Evaluator / metric', 'Before', 'After', 'Delta']) header.append(node('th', title));
  head.append(header); table.append(head);
  const body = node('tbody');
  for (const row of rows) {
    const delta = result.deltas?.find(x => x.evaluator_id === row.evaluator && x.metric_key === row.key);
    const tr = node('tr');
    for (const value of [row.evaluator + ' / ' + row.key, measurementText(row.before), measurementText(row.after), deltaText(delta, row.before, row.after)]) tr.append(node('td', value));
    body.append(tr);
  }
  table.append(body); wrap.append(table); section.append(wrap); return section;
}
