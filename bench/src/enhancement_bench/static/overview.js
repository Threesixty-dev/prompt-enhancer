import { node } from './forms.js';
import { assertionOutcome, attemptAssertionState } from './assertions.js';

const join = values => [...new Set(values)].join(' / ');
const count = (n, label) => `${n} ${label}${n === 1 ? '' : 's'}`;
const aspects = ['goal', 'scope', 'context', 'constraints', 'acceptance', 'deliverable'];

export function dimensions(settings) {
  const cases = settings.subjects?.length ?? settings.caseCount;
  const variants = settings.units?.length;
  return { cases, variants, attempts: cases == null || variants == null ? null : cases * variants };
}

export function countLabel(settings) {
  const { cases, variants, attempts } = dimensions(settings);
  return attempts === null ? 'Attempt count unknown' : `${count(cases, 'case')} \u00b7 ${count(variants, 'variant')} \u00b7 ${count(attempts, 'attempt')}`;
}

export function runLabel(run) {
  const settings = run.effective || run.configuration;
  if (!settings) return 'Run ' + run.id.slice(0, 8);
  const { cases, variants } = dimensions(settings);
  const subjectIds = settings.subjects?.map(subject => subject.id) ?? settings.subjectIds;
  const workflow = settings.workflow?.workflow_id;
  const name = { 'prompt-check': 'Prompt Check', 'prompt-rewrite': 'Prompt Rewrite', 'prompt-clarify': 'Prompt Clarify' }[workflow] || workflow || 'Run';
  const selectedCase = cases === 1 && subjectIds?.length === 1 ? subjectIds[0] : cases == null ? 'Cases unknown' : count(cases, 'case');
  const selectedVariant = variants === 1 ? settings.units[0].id : variants == null ? 'Variants unknown' : count(variants, 'variant');
  return [name, selectedCase, selectedVariant].join(' \u00b7 ');
}

export function generationLabel(settings, unit) {
  if (unit.strategy === 'script.clarify.v1') return 'No model (packaged script)';
  if (!unit.strategy?.startsWith('consumer.') && unit.strategy !== 'prompt.check.v1') return 'Unknown';
  const stepId = unit.strategy === 'prompt.check.v1' ? 'review' : 'rewrite';
  const step = { ...settings.baseStepSettings?.[stepId], ...unit.stepSettings?.[stepId] };
  const binding = step.binding || unit.stepBindings?.[stepId] || { ...settings.consumerBinding, ...unit.consumerBinding };
  if (unit.strategy === 'prompt.check.v1' && !binding.binding_id) return 'No model (diagnostics only)';
  return `${binding.binding_id || 'Unknown alias'} (${binding.provider || 'unknown provider'})`;
}

export function evaluationLabel(evaluator) {
  return evaluator.kind === 'deterministic' ? `No model (deterministic: ${evaluator.binding_id || 'unknown binding'})`
    : `${evaluator.binding_id || 'Unknown alias'} (${evaluator.kind || 'unknown kind'})`;
}

export function modelSummary(settings) {
  const box = node('dl', undefined, 'model-summary');
  for (const [label, value] of [
    ['Generation model aliases', join((settings?.units || []).map(unit => generationLabel(settings, unit))) || 'Unknown'],
    ['Evaluation model aliases', join((settings?.evaluatorProfile?.evaluators || []).map(evaluationLabel)) || 'Unknown'],
  ]) {
    const row = node('div'); row.append(node('dt', label), node('dd', value)); box.append(row);
  }
  return box;
}

export function variantDescription(settings, unit) {
  if (unit.strategy === 'prompt.check.v1') {
    const focus = { 'prompt-rewrite': 'Review focus: rewriting for clarity and testability.', 'prompt-clarify': 'Review focus: missing details and clarification questions.' };
    return focus[settings.workflow?.workflow_id] || 'Prompt review with deterministic findings and optional model commentary.';
  }
  const steering = { ...settings.baseSteering, ...unit.steering };
  const focus = steering.focus?.length ? steering.focus : aspects;
  if (unit.strategy === 'script.clarify.v1') {
    return `Clarification focus: ${focus.join(', ')}. Adds placeholders where needed${steering.profile === 'targeted.v1' ? ', restricted by objective targets when present' : ''}.`;
  }
  return `Style: ${steering.style || 'unknown'}. Focus: ${focus.join(', ')}.`;
}

export const attemptAnchor = id => 'attempt-' + id;

export function variationOverview(settings, { attempts, onAttempt } = {}) {
  const section = node('section', undefined, 'surface variation-overview');
  section.setAttribute('aria-label', 'Run variations');
  section.append(node('p', attempts ? 'This run' : 'Run design', 'eyebrow'), node('h2', 'Run variations'));
  const summary = node('p', countLabel(settings), 'variation-count');
  summary.setAttribute('aria-live', 'polite'); section.append(summary);
  const { cases, variants, attempts: total } = dimensions(settings);
  const equation = node('div', undefined, 'variation-equation'); equation.setAttribute('aria-hidden', 'true');
  for (const [index, [value, label]] of [[cases, 'Input cases'], [variants, 'Variants'], [total, 'Attempts']].entries()) {
    if (index) equation.append(node('span', index === 1 ? '\u00d7' : '=', 'variation-operator'));
    const tile = node('div', undefined, 'variation-factor'); tile.append(node('strong', String(value)), node('span', label)); equation.append(tile);
  }
  section.append(equation, node('p', 'Each input case is paired with every selected variant (experiment unit). Before / After compares the original and enhanced prompt within one attempt; it does not add cases.', 'hint'));
  if (!total) { section.append(node('p', 'Select at least one input case and one variant to preview the attempts.', 'empty')); return section; }
  const scroll = node('div', undefined, 'table-scroll variation-scroll'); scroll.tabIndex = 0;
  scroll.setAttribute('role', 'region'); scroll.setAttribute('aria-label', 'Cases by variants, scroll to see all variants');
  const table = node('table', undefined, 'variation-matrix');
  table.append(node('caption', (attempts ? 'Select an attempt to inspect its result.' : 'Planned attempts in execution order.') + ' Scroll horizontally to compare more variants.'));
  const head = node('thead'), header = node('tr'); const corner = node('th', 'Input case'); corner.scope = 'col'; header.append(corner);
  for (const unit of settings.units) {
    const th = node('th'); th.scope = 'col'; th.append(node('strong', unit.title), node('small', unit.strategy), node('small', variantDescription(settings, unit)), node('small', generationLabel(settings, unit))); header.append(th);
  }
  head.append(header); table.append(head); const body = node('tbody');
  const recorded = new Map((attempts || []).map(attempt => [JSON.stringify([attempt.subject_id, attempt.unit_id]), attempt]));
  let ordinal = 0;
  for (const subject of settings.subjects) {
    const row = node('tr'), name = node('th'); name.scope = 'row'; name.append(node('strong', subject.id), node('span', subject.text, 'case-preview')); row.append(name);
    const prompt = node('details', undefined, 'prompt-disclosure case-prompt'); prompt.dataset.key = 'case:' + subject.id;
    const toggle = node('summary'); toggle.append(node('span', 'Expand prompt', 'prompt-expand'), node('span', 'Collapse prompt', 'prompt-collapse'));
    const full = node('div', subject.text, 'case-full'); full.tabIndex = 0; full.setAttribute('aria-label', 'Full prompt for ' + subject.id);
    prompt.append(toggle, full); name.append(prompt);
    for (const unit of settings.units) {
      ordinal++;
      const cell = node('td'), attempt = recorded.get(JSON.stringify([subject.id, unit.id]));
      const content = node(attempt ? 'a' : 'div', undefined, 'attempt-cell');
      const number = attempt ? (attempt.position == null ? attempts.indexOf(attempt) : attempt.position) + 1 : ordinal;
      content.append(node('strong', `Attempt ${number}`), node('span', attempts ? attempt?.status || 'Not recorded' : 'Planned', 'attempt-state'));
      if (attempt) {
        const outcome = assertionOutcome(attemptAssertionState(attempt));
        content.querySelector('.attempt-state').textContent = 'Execution: ' + attempt.status;
        content.append(outcome);
        content.href = '#' + attemptAnchor(attempt.id); content.dataset.status = attempt.status;
        content.dataset.assertionOutcome = outcome.dataset.outcome;
        content.setAttribute('aria-label', `Attempt ${number}: ${subject.id}, ${unit.title}, execution: ${attempt.status}, ${outcome.textContent}`);
        content.onclick = event => { if (event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { event.preventDefault(); onAttempt?.(attempt); } };
      }
      cell.append(content); row.append(cell);
    }
    body.append(row);
  }
  table.append(body); scroll.append(table); section.append(scroll); return section;
}

export function modelEvidence(result) {
  const box = node('div', undefined, 'model-evidence'); box.append(node('h3', 'Recorded model details'));
  const entries = [['Generation', result?.consumer_provenance]];
  for (const step of result?.workflow_result?.steps || []) if (step.provenance) entries.push([`Workflow step: ${step.step_id}`, step.provenance]);
  for (const side of ['before', 'after']) for (const evaluator of result?.[side] || []) entries.push([`${side === 'before' ? 'Before' : 'After'} evaluator: ${evaluator.evaluator_id}`, evaluator.provenance]);
  for (const [label, provenance] of entries) {
    const card = node('div', undefined, 'model-evidence-card'); card.append(node('h4', label));
    const facts = node('dl', undefined, 'model-summary');
    const noModel = provenance?.identity_source === 'not_applicable' && ['packaged_script', 'deterministic'].includes(provenance?.provider);
    for (const [key, value] of [
      ['Provider', provenance?.provider], ['Model', noModel ? 'No model' : provenance?.model],
      ['Reported model', noModel ? 'Not applicable' : provenance?.reported_model],
      ['Model revision', noModel ? 'Not applicable' : provenance?.model_revision],
      ['Identity source', provenance?.identity_source],
    ]) { const row = node('div'); row.append(node('dt', key), node('dd', value || 'Unknown')); facts.append(row); }
    card.append(facts); box.append(card);
  }
  return box;
}
