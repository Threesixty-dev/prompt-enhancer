import { node, schemaField } from './forms.js';

const kinds = {
  deterministic: 'Rule-based (no model)', rubric: 'Rubric model',
  classifier: 'Classifier model', embedding: 'Embedding model',
};

export function evaluatorEditor(profile, schema, experiments) {
  const section = node('section', undefined, 'surface'); section.id = 'evaluator-editor';
  section.append(node('h2', 'Evaluators'), node('p', 'Choose which models evaluate the prompts. Every evaluator runs before and after each rewrite, with the same settings for all variants.', 'hint'),
    node('p', 'Rule-based scores and model judgments are separate measurements. Keep any evaluator referenced by the experiment’s assertions or objective targets.', 'hint'));
  const list = node('div', undefined, 'array-items'), add = node('button', 'Add evaluator', 'secondary'); add.type = 'button';
  const rows = []; let serial = 0;
  const spec = schema.$defs.Evaluator, options = { definitions: schema.$defs };
  const changed = () => section.dispatchEvent(new Event('change', { bubbles: true }));
  const update = () => {
    add.disabled = rows.length >= schema.$defs.EvaluationProfile.properties.evaluators.maxItems;
    for (const row of rows) row.remove.disabled = rows.length <= 1;
  };
  const append = initial => {
    const index = ++serial, prefix = `evaluator-${index}`, card = node('fieldset', undefined, 'field-group');
    card.dataset.evaluator = String(index); card.append(node('legend', `Evaluator ${index}`));
    const id = schemaField(spec.properties.evaluator_id, initial.evaluator_id, { ...options, id: prefix + '-id', label: 'Evaluator ID' });
    const typeLabel = node('label', 'Evaluation method'), type = node('select'); type.id = prefix + '-kind'; typeLabel.htmlFor = type.id;
    for (const kind of spec.properties.kind.enum) { const option = node('option', kinds[kind]); option.value = kind; type.append(option); }
    type.value = initial.kind;
    const details = node('div', undefined, 'form-grid'); let binding, rubric, target, generation;
    const render = value => {
      details.replaceChildren(); rubric = target = generation = undefined;
      binding = schemaField(spec.properties.binding_id, value.binding_id, { ...options, id: prefix + '-binding', label: type.value === 'deterministic' ? 'Rule binding' : 'Evaluator model alias' });
      details.append(binding.element);
      const aliases = [...new Set([...(profile.evaluators || []), ...experiments.flatMap(d => d.evaluatorProfile?.evaluators || [])]
        .filter(e => e.kind === type.value).map(e => e.binding_id))];
      const choices = node('datalist'); choices.id = prefix + '-aliases';
      for (const alias of aliases) { const option = node('option'); option.value = alias; choices.append(option); }
      binding.element.querySelector('input').setAttribute('list', choices.id); details.append(choices);
      if (type.value === 'rubric') {
        rubric = schemaField(spec.properties.rubric.anyOf.find(s => s.type === 'string'), value.rubric, { ...options, id: prefix + '-rubric', label: 'Evaluation criterion' });
        generation = schemaField(spec.properties.generation, value.generation, { ...options, id: prefix + '-generation', label: 'Evaluation generation', required: false });
        const advanced = node('details'); advanced.append(node('summary', 'Evaluator generation settings'), generation.element);
        details.append(rubric.element, advanced, node('p', 'Rubric models return present, absent, or unknown for the selected criterion. They do not replace the rule-based numeric scores.', 'hint'));
      } else if (['classifier', 'embedding'].includes(type.value)) {
        target = schemaField(spec.properties.target.anyOf.find(s => s.type === 'string'), value.target, { ...options, id: prefix + '-target', label: type.value === 'classifier' ? 'Statement to classify' : 'Reference text' });
        details.append(target.element);
      }
      if (type.value !== 'deterministic') details.append(node('p', 'Use an operator-configured alias, such as the Qwen evaluator alias from your experiment definitions. Suggestions come from saved definitions; the core checks availability when the run starts. Endpoints and credentials are configured outside the run.', 'hint'));
    };
    const read = () => {
      const value = initial.kind === type.value ? { ...initial } : {};
      Object.assign(value, { evaluator_id: id.read(), kind: type.value, binding_id: binding.read() });
      for (const [key, field] of Object.entries({ target, rubric, generation })) {
        if (field) { const setting = field.read(); if (setting === undefined) delete value[key]; else value[key] = setting; }
      }
      return value;
    };
    type.onchange = () => { render({ binding_id: type.value === 'deterministic' ? 'deterministic.v1' : '', rubric: 'acceptance_testability' }); changed(); };
    render(initial);
    const remove = node('button', 'Remove evaluator', 'secondary'); remove.type = 'button'; remove.setAttribute('aria-label', `Remove evaluator ${index}`);
    const row = { read, remove }; rows.push(row);
    remove.onclick = () => { rows.splice(rows.indexOf(row), 1); card.remove(); update(); changed(); add.focus(); };
    card.append(id.element, typeLabel, type, details, remove); list.append(card); update();
  };
  for (const evaluator of profile.evaluators) append(evaluator);
  add.onclick = () => {
    const ids = new Set(rows.map(row => row.read().evaluator_id)); let index = serial + 1;
    while (ids.has(`evaluator-${index}`)) index++;
    append({ evaluator_id: `evaluator-${index}`, kind: 'rubric', binding_id: '', rubric: 'acceptance_testability' });
    changed(); list.lastElementChild.querySelector('input').focus();
  };
  section.append(list, add);
  return { element: section, read: () => rows.map(row => row.read()) };
}

export const evaluatorErrors = {
  duplicate_evaluator: 'Give each evaluator a unique ID.',
  invalid_evaluator_settings: 'Choose the settings required by each evaluation method.',
  referenced_evaluator_required: 'Keep evaluators referenced by the experiment’s assertions and selected objective targets. Add model evaluators alongside them.',
  evaluator_metric_incompatible: 'An evaluator’s method must support the metrics referenced by assertions and objective targets. Add a separate evaluator for a different method.',
};
