import { node } from './forms.js';
import { countLabel, evaluationLabel, generationLabel, variantDescription } from './overview.js';

function card(title, text, kind = '') {
  const box = node('div', undefined, 'flow-card ' + kind);
  box.append(node('h3', title));
  if (text) box.append(node('p', text));
  return box;
}

function evaluatorOrder(settings, side) {
  const list = node('ol', undefined, 'flow-evaluators');
  list.setAttribute('aria-label', side + ' evaluator order');
  for (const evaluator of settings.evaluatorProfile?.evaluators || []) {
    const item = node('li');
    item.append(node('strong', evaluator.evaluator_id), node('span', evaluationLabel(evaluator)));
    list.append(item);
  }
  if (!list.children.length) list.append(node('li', 'Evaluator order unknown.'));
  return list;
}

function generationSettings(settings, unit, manifest) {
  const stepId = manifest?.model_step || (unit.strategy === 'prompt.check.v1' ? 'review' : 'rewrite');
  const step = { ...settings.baseStepSettings?.[stepId], ...unit.stepSettings?.[stepId] };
  const generation = step.generation || unit.parameters?.generation || settings.baseParameters?.generation || {};
  const values = {};
  for (const key of ['max_tokens', 'temperature']) values[key] = Object.hasOwn(generation, key)
    ? generation[key] : manifest?.defaults?.[key];
  const label = value => value === null ? 'provider managed (unknown)' : value === undefined ? 'unknown' : String(value);
  const text = node('p', `Token limit: ${label(values.max_tokens)}. Temperature: ${label(values.temperature)}.`, 'hint');
  const policy = step.policy ? `${step.policy.policy_id} / ${step.policy.revision}` : manifest?.defaults?.policy_version || 'Not recorded';
  return [node('p', 'Policy: ' + policy, 'hint'), text];
}

function flowFor(settings, unit, manifest) {
  const figure = node('figure', undefined, 'experiment-flow-figure');
  figure.append(node('figcaption', `Planned flow for ${unit.title}. Recorded attempt receipts show what actually executed.`));
  figure.append(card('Input', 'One case: original prompt and explicitly supplied context.'));
  const sequence = node('ol', undefined, 'flow-sequence');
  sequence.setAttribute('aria-label', 'Experiment execution order');
  const add = (title, text) => { const item = node('li'), box = card(title, text); item.append(box); sequence.append(item); return box; };
  const before = add('1. Evaluate original', 'Harness: run these evaluators sequentially on the original input.');
  before.append(evaluatorOrder(settings, 'Before'));
  const workflow = add('2. Run workflow', manifest?.presentation?.title || (settings.workflow ? 'Workflow manifest unavailable for this exact revision.' : 'Legacy strategy: ' + unit.strategy));
  const logic = node('ol', undefined, 'flow-logic'); logic.setAttribute('aria-label', 'Diagram workflow steps');
  const legacySteps = { 'consumer.rewrite.v1': ['Send original input and harness baseline to generation', 'Validate candidate'],
    'script.clarify.v1': ['Add clarification placeholders with the packaged script'] };
  for (const text of manifest?.presentation?.logic_steps || (!settings.workflow && legacySteps[unit.strategy]) || ['Workflow order unknown']) logic.append(node('li', text));
  workflow.append(logic, node('p', variantDescription(settings, unit), 'hint'));
  const generation = generationLabel(settings, unit);
  const diagnosticsOnly = unit.strategy === 'prompt.check.v1' && generation.startsWith('No model');
  workflow.append(node('p', 'Generation: ' + generation, 'flow-binding'));
  if (generation.startsWith('No model')) workflow.append(node('p', unit.strategy === 'prompt.check.v1'
    ? 'The review step is skipped; retain workflow diagnostics and context.' : 'The packaged script computes the output.', 'hint'));
  else workflow.append(...generationSettings(settings, unit, manifest));
  if (manifest) workflow.append(node('p', unit.strategy === 'prompt.check.v1'
    ? 'The workflow receives its own diagnostics and inferred context. Harness scores are kept outside its model input.'
    : 'The workflow computes its own diagnostics. Harness scores are kept outside its input.', 'hint'));
  const after = add('3. Follow the output branch');
  const branches = node('div', undefined, 'flow-branches');
  const candidate = card('Valid candidate', 'Evaluate the candidate with the same profile and order.', 'flow-success');
  candidate.append(evaluatorOrder(settings, 'After'));
  const absent = card('Valid result without a candidate', 'Keep findings and diagnostics. After measurements are absent; comparison values remain unavailable.', 'flow-neutral');
  const failed = card(diagnosticsOnly ? 'Technical failure' : 'Invalid review or technical failure', 'Record a failed attempt and its safe reason. Keep completed evidence; produce no fabricated after scores.', 'flow-failure');
  if (diagnosticsOnly) branches.append(absent, failed);
  else if (unit.strategy === 'prompt.check.v1') branches.append(candidate, absent, failed);
  else branches.append(candidate, failed);
  after.append(branches);
  add('4. Compare and store', (diagnosticsOnly ? 'Comparisons and applicable assertions remain unavailable without a candidate. '
    : 'When a candidate exists, compute comparable deltas and evaluate assertions. ')
    + 'Store outputs, explicit metric states, timings and provenance for the API, UI and private export.');
  figure.append(sequence, card('Recovery gate', 'Uncertain execution or unconfirmed cleanup holds the queue for operator reconciliation. A completed invalid response stays failed; inspect continuation guidance before another independent case.', 'flow-recovery'));
  return figure;
}

export function experimentFlow(settings, manifest) {
  const section = node('section', undefined, 'surface experiment-flow');
  section.setAttribute('aria-label', 'Experiment flow');
  section.append(node('p', 'Definition and data flow', 'eyebrow'), node('h2', 'Experiment flow'),
    node('p', countLabel(settings) + '. Each case follows this flow once per selected variant.', 'hint'));
  const units = settings.units || [];
  if (!units.length) { section.append(node('p', 'Select a variant to inspect its flow.')); return section; }
  const label = node('label', 'Flow variant');
  const select = node('select'); select.id = 'flow-variant'; select.dataset.preserve = 'flow-variant'; label.htmlFor = select.id;
  for (const unit of units) { const option = node('option', unit.title); option.value = unit.id; select.append(option); }
  const holder = node('div'); holder.setAttribute('aria-live', 'polite');
  const update = () => holder.replaceChildren(flowFor(settings, units.find(unit => unit.id === select.value) || units[0], manifest));
  select.addEventListener('change', update); update();
  section.append(label, select, holder);
  return section;
}
