import { node } from './forms.js';
import { measurementText, deltaText } from './metrics.js';

const labels = { passed: 'Passed', failed: 'Failed', unknown: 'Unknown', not_evaluated: 'Not evaluated', not_recorded: 'Not recorded' };
const state = outcome => Object.hasOwn(labels, outcome) ? outcome : 'not_recorded';
const numeric = value => typeof value === 'number' && Number.isFinite(value) ? String(value) : 'Not recorded';
const reading = metric => metric?.state === 'known' && typeof metric.value === 'number' ? numeric(metric.value) : measurementText(metric);
const sameAssertion = (a, b) => ['evaluator_id', 'metric_key', 'operator', 'threshold'].every(key => a?.[key] === b?.[key]);

export function assertionOutcome(outcome) {
  const label = node('span', 'Assertions: ' + labels[state(outcome)], 'assertion-outcome');
  label.dataset.outcome = state(outcome); return label;
}

export const attemptAssertionState = attempt => attempt.result?.assertion_outcome
  ?? (['queued', 'running'].includes(attempt.status) ? 'not_evaluated' : 'not_recorded');

function checksFor(attempt, unit) {
  const recorded = [...(attempt.result?.assertions || [])];
  const checks = (unit?.assertions || []).map(assertion => {
    const index = recorded.findIndex(check => sameAssertion(check.assertion, assertion));
    return index < 0 ? { assertion, outcome: attempt.result ? 'not_recorded' : 'not_evaluated', observed: null }
      : recorded.splice(index, 1)[0];
  });
  return [...checks, ...recorded];
}

function expected(assertion) {
  const quantity = { minimum_value: 'After value', minimum_delta: 'Change (after - before)' }[assertion.operator];
  return quantity ? quantity + ' >= ' + numeric(assertion.threshold) : 'Unrecognized rule: ' + (assertion.operator || 'not recorded');
}

export function attemptAssertions(attempt, unit) {
  const section = node('section', undefined, 'attempt-assertions');
  section.setAttribute('aria-label', 'Attempt quality assertions');
  section.append(node('h3', 'Quality assertions'), assertionOutcome(attemptAssertionState(attempt)));
  const checks = checksFor(attempt, unit);
  if (!checks.length) {
    section.append(node('p', Array.isArray(unit?.assertions) ? 'No quality assertions configured for this attempt.' : 'Assertion configuration not recorded.', 'hint'));
    return section;
  }
  const list = node('ul', undefined, 'assertion-checks');
  for (const check of checks) {
    const assertion = check.assertion, outcome = state(check.outcome);
    const item = node('li', undefined, 'assertion-check'); item.dataset.outcome = outcome;
    const heading = node('div', undefined, 'assertion-heading');
    heading.append(node('strong', assertion.metric_key), node('span', labels[outcome], 'assertion-state'));
    item.append(heading, node('p', 'Evaluator: ' + assertion.evaluator_id, 'hint'));
    const facts = node('dl', undefined, 'assertion-facts');
    for (const [label, value] of [['Expected', expected(assertion)], ['Observed', numeric(check.observed)]]) {
      const pair = node('div'); pair.append(node('dt', label), node('dd', value)); facts.append(pair);
    }
    item.append(facts);
    const before = attempt.result?.before?.find(e => e.evaluator_id === assertion.evaluator_id)?.metrics?.find(m => m.key === assertion.metric_key);
    const after = attempt.result?.after?.find(e => e.evaluator_id === assertion.evaluator_id)?.metrics?.find(m => m.key === assertion.metric_key);
    const delta = attempt.result?.deltas?.find(d => d.evaluator_id === assertion.evaluator_id && d.metric_key === assertion.metric_key);
    item.append(node('p', 'Before: ' + reading(before) + ' / After: ' + reading(after), 'hint assertion-context'));
    if (outcome === 'unknown') item.append(node('p', assertion.operator === 'minimum_delta'
      ? deltaText(delta, before, after) : 'After measurement: ' + reading(after), 'hint'));
    if (outcome === 'failed') item.append(node('p', 'Measured value does not meet the configured requirement.', 'assertion-explanation'));
    if (outcome === 'not_recorded') item.append(node('p', 'This configured assertion has no recorded result.', 'hint'));
    if (outcome === 'not_evaluated') item.append(node('p', 'No assertion result is available for this attempt yet.', 'hint'));
    list.append(item);
  }
  section.append(list); return section;
}

export function qualitySummary(run, onAttempt) {
  const section = node('section', undefined, 'surface quality-summary');
  section.setAttribute('aria-label', 'Run quality assertions');
  const counts = Object.fromEntries(Object.keys(labels).map(key => [key, 0])), failures = [];
  let configurationMissing = false;
  for (const [index, attempt] of run.attempts.entries()) {
    const unit = run.effective.units.find(u => u.id === attempt.unit_id);
    configurationMissing ||= !Array.isArray(unit?.assertions);
    for (const check of checksFor(attempt, unit)) {
      counts[state(check.outcome)]++;
      if (check.outcome === 'failed') failures.push({ attempt, unit, check, number: (attempt.position ?? index) + 1 });
    }
  }
  section.dataset.outcome = failures.length ? 'failed' : state(run.assertion_outcome);
  section.append(node('h2', 'Quality assertions'), assertionOutcome(run.assertion_outcome));
  section.append(node('p', 'Execution: ' + run.status + '. Quality assertions check configured metric requirements. Unknown results remain unresolved.', 'hint'));
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  if (total) section.append(node('p', Object.entries(counts).filter(([, count]) => count).map(([key, count]) => count + ' ' + labels[key].toLowerCase()).join(' \u00b7 '), 'assertion-counts'));
  else section.append(node('p', configurationMissing ? 'Assertion configuration not recorded.' : 'No quality assertions configured for this run.', 'hint'));
  if (configurationMissing && total) section.append(node('p', 'Some assertion configuration is missing; these counts cover available checks only.', 'hint'));
  if (failures.length) {
    section.append(node('h3', failures.length + ' failed quality assertion' + (failures.length === 1 ? '' : 's')));
    const list = node('ul', undefined, 'assertion-failures');
    for (const { attempt, unit, check, number } of failures) {
      const item = node('li'), anchor = node('a', 'Attempt ' + number + ': ' + attempt.subject_id + ' / ' + (unit?.title || attempt.unit_id));
      anchor.href = '#attempt-' + attempt.id;
      anchor.onclick = event => { if (event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { event.preventDefault(); onAttempt(attempt); } };
      item.append(anchor, node('p', check.assertion.metric_key + ': expected ' + expected(check.assertion) + '; observed ' + numeric(check.observed) + '.', 'assertion-failure-detail'));
      list.append(item);
    }
    section.append(list);
  } else if (run.assertion_outcome === 'failed') section.append(node('p', 'The run records a failed assertion, but individual failed-check details are unavailable.', 'assertion-explanation'));
  return section;
}
