export const node = (tag, text, className) => {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
};

const labels = {
  timeout_seconds: 'Timeout (seconds)', max_output_chars: 'Maximum output characters',
  max_tokens: 'Maximum tokens', binding_id: 'Model alias', objective_id: 'Objective ID',
  desired_value: 'Desired value', desired_label: 'Desired label', evaluator_id: 'Evaluator ID',
};
export const labelFor = key => labels[key] || key.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase());

function resolve(schema, definitions) {
  if (!schema.$ref) return schema;
  const prefix = '#/$defs/';
  if (!schema.$ref.startsWith(prefix) || !definitions[schema.$ref.slice(prefix.length)]) {
    throw new Error('This experiment uses an unsupported form schema.');
  }
  return resolve(definitions[schema.$ref.slice(prefix.length)], definitions);
}

// Reads return typed values. An absent value remains absent; null is an explicit choice.
export function schemaField(schema, value, { id, label, definitions = {}, required = true, depth = 0 }) {
  if (depth > 12) throw new Error('This experiment has too many nested parameter groups.');
  schema = resolve(schema, definitions);
  const options = { definitions, depth: depth + 1 };
  const variants = schema.oneOf || schema.anyOf;
  const nullable = Array.isArray(schema.type) ? schema.type.includes('null') : variants?.some(s => s.type === 'null');
  if (nullable || (!required && value === undefined)) {
    const types = Array.isArray(schema.type) ? schema.type.filter(t => t !== 'null') : null;
    const concrete = types ? { ...schema, type: types[0] } : (variants || []).find(s => s.type !== 'null') || schema;
    const wrapper = node('div', undefined, 'optional-field');
    const modeLabel = node('label', `${label} setting`); modeLabel.htmlFor = `${id}-mode`;
    const mode = node('select'); mode.id = `${id}-mode`;
    const choices = [['value', 'Set a value']];
    if (nullable) choices.push(['null', ['max_tokens', 'temperature'].some(key => id.endsWith(key)) ? 'Provider default (unknown)' : 'Not specified (null)']);
    if (!required) choices.push(['absent', 'Keep unspecified']);
    for (const [key, text] of choices) { const option = node('option', text); option.value = key; mode.append(option); }
    mode.value = value === undefined && !required ? 'absent' : value === null ? 'null' : 'value';
    const inner = schemaField(concrete, value ?? undefined, { ...options, id, label, required: true });
    const group = node('fieldset', undefined, 'value-field'); group.append(inner.element);
    const update = () => { group.disabled = mode.value !== 'value'; group.hidden = group.disabled; };
    mode.onchange = update; update(); wrapper.append(modeLabel, mode, group);
    return { element: wrapper, read: () => mode.value === 'null' ? null : mode.value === 'absent' ? undefined : inner.read() };
  }
  if (variants) {
    const schemas = variants.map(s => resolve(s, definitions));
    const wrapper = node('div', undefined, 'variant-field');
    const kindLabel = node('label', `${label} type`); kindLabel.htmlFor = `${id}-type`;
    const select = node('select'); select.id = `${id}-type`;
    schemas.forEach((s, index) => { const option = node('option', labelFor(s.properties?.kind?.const || s.title || String(index + 1))); option.value = String(index); select.append(option); });
    select.value = String(Math.max(0, schemas.findIndex(s => s.properties?.kind?.const === value?.kind)));
    const holder = node('div'); let current;
    const update = initial => { current = schemaField(schemas[Number(select.value)], initial, { ...options, id, label }); holder.replaceChildren(current.element); };
    select.onchange = () => update(undefined); update(value); wrapper.append(kindLabel, select, holder);
    return { element: wrapper, read: () => current.read() };
  }
  if (schema.type === 'object') {
    const group = node('fieldset', undefined, 'field-group'); group.append(node('legend', label));
    const grid = node('div', undefined, 'form-grid');
    const fields = Object.entries(schema.properties || {}).map(([key, child]) => {
      const field = schemaField(child, value?.[key], { ...options, id: `${id}-${key}`, label: labelFor(key), required: schema.required?.includes(key) || false });
      grid.append(field.element); return [key, field];
    });
    group.append(grid);
    return { element: group, read: () => Object.fromEntries(fields.map(([key, field]) => [key, field.read()]).filter(([, v]) => v !== undefined)) };
  }
  if (schema.type === 'array') {
    const group = node('fieldset', undefined, 'field-group'); group.append(node('legend', label));
    const items = resolve(schema.items || {}, definitions);
    if (items.enum) {
      const inputs = items.enum.map((item, index) => {
        const line = node('label', undefined, 'check-option'); const input = node('input'); input.type = 'checkbox'; input.id = `${id}-${index}`;
        input.checked = (value || []).includes(item); line.append(input, node('span', labelFor(item))); group.append(line); return [item, input];
      });
      return { element: group, read: () => inputs.filter(([, input]) => input.checked).map(([item]) => item) };
    }
    const list = node('div', undefined, 'array-items'), add = node('button', `Add ${label.toLowerCase().replace(/s$/, '')}`, 'secondary'); add.type = 'button';
    const rows = []; let serial = 0;
    const update = () => { add.disabled = rows.length >= (schema.maxItems ?? 32); rows.forEach(row => { row.remove.disabled = rows.length <= (schema.minItems || 0); }); };
    const append = initial => {
      const field = schemaField(items, initial, { ...options, id: `${id}-${++serial}`, label: `${label} item` });
      const row = node('div', undefined, 'array-row'), remove = node('button', 'Remove', 'secondary'); remove.type = 'button'; remove.setAttribute('aria-label', `Remove ${label.toLowerCase()} item ${serial}`);
      const entry = { field, remove }; rows.push(entry); row.append(field.element, remove); list.append(row);
      remove.onclick = () => { rows.splice(rows.indexOf(entry), 1); row.remove(); update(); }; update();
    };
    for (const item of value || []) append(item);
    while (rows.length < (schema.minItems || 0)) append(undefined);
    add.onclick = () => append(undefined); update(); group.append(list, add);
    return { element: group, read: () => rows.map(row => row.field.read()) };
  }
  if ('const' in schema) return { element: node('p', `${label}: ${schema.const}`, 'hint'), read: () => schema.const };
  if (!['string', 'number', 'integer', 'boolean'].includes(schema.type)) throw new Error(`No form control is available for ${label}.`);
  const wrapper = node('div', undefined, 'form-field'), caption = node('label', label); caption.htmlFor = id;
  let input;
  if (schema.enum || schema.type === 'boolean') {
    input = node('select');
    const values = schema.enum || [true, false];
    if (value === undefined) { const empty = node('option', 'Choose a value'); empty.value = ''; input.append(empty); }
    for (const item of values) { const option = node('option', typeof item === 'boolean' ? item ? 'Yes' : 'No' : labelFor(String(item))); option.value = JSON.stringify(item); input.append(option); }
    input.value = value === undefined ? '' : JSON.stringify(value);
  } else {
    input = node(schema.type === 'string' && (schema.maxLength || 0) > 500 ? 'textarea' : 'input');
    if (schema.type === 'number' || schema.type === 'integer') { input.type = 'number'; input.step = schema.type === 'integer' ? '1' : 'any'; }
    if (schema.minimum !== undefined) input.min = String(schema.minimum);
    if (schema.maximum !== undefined) input.max = String(schema.maximum);
    if (schema.minLength !== undefined) input.minLength = schema.minLength;
    if (schema.maxLength !== undefined) input.maxLength = schema.maxLength;
    if (schema.pattern) input.pattern = schema.pattern;
    input.value = value === undefined ? '' : String(value);
  }
  input.id = id; input.required = required; wrapper.append(caption, input);
  if (schema.description) wrapper.append(node('small', schema.description));
  if (schema.minimum !== undefined || schema.maximum !== undefined) wrapper.append(node('small', `Allowed: ${schema.minimum ?? 'no minimum'} to ${schema.maximum ?? 'no maximum'}.`));
  return { element: wrapper, read: () => {
    if (input.value === '' && !required) return undefined;
    if (schema.enum || schema.type === 'boolean') return input.value === '' ? undefined : JSON.parse(input.value);
    if (schema.type === 'number' || schema.type === 'integer') return input.value === '' ? undefined : Number(input.value);
    return input.value;
  } };
}

export function validateForm(form) {
  const invalid = [...form.elements].find(element => element.willValidate && !element.validity.valid);
  if (invalid) {
    for (let parent = invalid.parentElement; parent && parent !== form; parent = parent.parentElement) if (parent.tagName === 'DETAILS') parent.open = true;
    invalid.reportValidity(); return false;
  }
  return true;
}
