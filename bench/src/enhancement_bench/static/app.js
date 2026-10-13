"use strict";
const $ = (id) => document.getElementById(id);
let token = "", experiments = [], runs = [], selection = null, selectedRun = null, refreshBusy = false;
let pendingRequest = null;
const retryRequests = new Map();
const node = (tag, text, className) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (className) n.className = className; return n; };
const badge = (value) => node("span", value || "unknown", `badge ${value || "unknown"}`);
const json = (value) => JSON.stringify(value, null, 2);
const tell = (message) => { $("notice").textContent = message; };
async function api(path, body) {
  const response = await fetch(path, {method: body === undefined ? "GET" : "POST", cache: "no-store", headers: {Authorization: `Bearer ${token}`, "Content-Type": "application/json"}, body: body === undefined ? undefined : json(body)});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error?.code || "request_failed");
  return value;
}
function details(title, value) { const d = node("details"); d.append(node("summary", title), node("pre", json(value))); return d; }
function metadata(values) { const d = node("div", undefined, "meta"); for (const value of values) d.append(node("span", value)); return d; }
function showExperiments() {
  const container = $("experiments"); container.replaceChildren();
  const newest = new Map(); for (const d of experiments) if (!newest.has(d.stableId)) newest.set(d.stableId, d);
  for (const d of newest.values()) {
    const b = node("button", d.title, "experiment-choice"); b.type = "button"; b.setAttribute("aria-pressed", String(selection?.stableId === d.stableId)); b.append(node("span", `Revision ${d.revision} / ${d.units.length} Experiment Units`));
    b.onclick = () => { selection = d; pendingRequest = null; showExperiments(); showDefinition(); showRuns(); }; container.append(b);
  }
  if (!newest.size) container.append(node("p", "No Experiments imported yet.", "hint"));
}
function showDefinition() {
  const container = $("experiment"); container.replaceChildren();
  if (!selection) { container.append(node("div", "Publish a synthetic Experiment JSON from the experiments folder to begin.", "empty")); return; }
  const d = selection;
  const title = node("h2", d.title); title.id = "experiment-title";
  container.append(node("p", d.stableId, "eyebrow"), title, metadata([`Revision ${d.revision}`, `Generation ${d.generation}`, `Core ${d.enhancerVersion}`, `${d.subjects.length} Subjects`]));
  const form = node("form"); form.id = "run-form";
  const grid = node("div", undefined, "schema-form");
  const parameters = node("div"); const label = node("label", "Parameter overrides (JSON)"); label.htmlFor = "parameters";
  const field = node("textarea"); field.id = "parameters"; field.value = "{}"; field.spellcheck = false; parameters.append(label, field, node("small", "Only declared parameters are accepted. Effective settings are stored with the run."));
  const units = node("div"); const unitLabel = node("label", "Experiment Unit selection"); unitLabel.htmlFor = "unit-select";
  const select = node("select"); select.id = "unit-select"; const all = node("option", "All sibling Experiment Units"); all.value = ""; select.append(all);
  for (const unit of d.units) { const option = node("option", unit.title); option.value = unit.id; select.append(option); }
  units.append(unitLabel, select);
  for (const unit of d.units.filter(u => u.strategy.startsWith("consumer."))) units.append(node("p", `${unit.title}: ${unit.consumerBinding?.binding_id || d.consumerBinding?.binding_id || "unconfigured"}`, "hint"));
  units.append(node("p", `Evaluator: ${d.evaluatorProfile.profile_id} / ${d.evaluatorProfile.revision}`, "hint")); grid.append(parameters, units); form.append(grid);
  const advanced = node("details"), advancedGrid = node("div", undefined, "schema-form"); advanced.append(node("summary", "Objective and Experiment Unit steering"));
  const objectiveLabel = node("label", "Objective override (JSON)"); objectiveLabel.htmlFor = "objective-override";
  const objectiveField = node("textarea"); objectiveField.id = "objective-override"; objectiveField.value = "{}"; objectiveField.spellcheck = false;
  const steeringLabel = node("label", "Steering overrides by Experiment Unit ID (JSON)"); steeringLabel.htmlFor = "steering-overrides";
  const steeringField = node("textarea"); steeringField.id = "steering-overrides"; steeringField.value = "{}"; steeringField.spellcheck = false;
  const bindingLabel = node("label", "Consumer bindings by Experiment Unit ID (JSON)"); bindingLabel.htmlFor = "consumer-bindings";
  const bindingField = node("textarea"); bindingField.id = "consumer-bindings"; bindingField.value = "{}"; bindingField.spellcheck = false;
  const bindingBox = node("div"); bindingBox.append(bindingLabel, bindingField, node("small", "Select configured model aliases with binding_id. Provider defaults are inherited; endpoints and credentials are not accepted."));
  const objectiveBox = node("div"), steeringBox = node("div"); objectiveBox.append(objectiveLabel, objectiveField); steeringBox.append(steeringLabel, steeringField); advancedGrid.append(objectiveBox, steeringBox, bindingBox); advanced.append(advancedGrid, node("p", "Targets guide generation; assertions decide pass/fail. Consumer steering supports style and instructions. Scripted strategies accept only their declared controls.", "hint")); form.append(advanced);
  const actions = node("div", undefined, "actions"); const runButton = node("button", "Run with these settings"); runButton.type = "submit"; actions.append(node("p", "A UI run does not change the GitOps revision.", "hint"), runButton); form.append(actions);
  form.onsubmit = async (event) => { event.preventDefault(); runButton.disabled = true; try {
    const overrides = {parameters: JSON.parse(field.value), unitParameters: {}, objective: JSON.parse(objectiveField.value), unitSteering: JSON.parse(steeringField.value), unitConsumerBindings: JSON.parse(bindingField.value)}; if (select.value) overrides.unitIds = [select.value];
    const binding = json({stableId: d.stableId, revision: d.revision, overrides});
    if (!pendingRequest || pendingRequest.binding !== binding) pendingRequest = {binding, id: crypto.randomUUID()};
    const response = await api("/api/runs", {stableId: d.stableId, revision: d.revision, requestId: pendingRequest.id, overrides}); selectedRun = response.runId; pendingRequest = null; tell("Run queued. Its effective settings are now immutable."); await refresh();
  } catch (error) { tell(error.message); } finally { runButton.disabled = false; } };
  container.append(form, details("Experiment, image digest and parameter schema", d));
}
function showRuns() {
  const container = $("runs"); container.replaceChildren(); const visible = runs.filter(r => !selection || r.stable_id === selection.stableId); $("run-count").textContent = `${visible.length} recent runs`;
  for (const r of visible) { const button = node("button", undefined, "run-card"); button.append(node("span", `${r.origin === "gitops" ? "Automatic" : "Manual"} / revision ${r.revision} / ${r.id.slice(0, 8)}`), badge(r.status), node("span", new Date(r.created * 1000).toLocaleString(), "hint run-time")); button.onclick = async () => { selectedRun = r.id; try { await showRun(); $("run-detail").scrollIntoView({behavior: "smooth", block: "start"}); } catch(error) { tell(error.message); } }; container.append(button); }
  if (!visible.length) container.append(node("p", "No runs for this experiment yet.", "empty"));
}
function metricsTable(result) {
  const wrap = node("div", undefined, "table-scroll"), table = node("table"), head = node("thead"), tr = node("tr");
  for (const title of ["Evaluator / metric", "Before", "After", "Delta"]) tr.append(node("th", title)); head.append(tr); table.append(head);
  const body = node("tbody"); const display = metric => !metric ? "unknown" : metric.state !== "known" && metric.value == null ? `${metric.state}${metric.reason ? ` (${metric.reason})` : ""}` : typeof metric.value === "number" ? new Intl.NumberFormat(undefined,{maximumFractionDigits:4}).format(metric.value) : metric.label ?? "unknown";
  for (const evaluator of result.before || []) for (const metric of evaluator.metrics || []) {
    const after = result.after?.find(x => x.evaluator_id === evaluator.evaluator_id)?.metrics.find(x => x.key === metric.key);
    const delta = result.deltas?.find(x => x.evaluator_id === evaluator.evaluator_id && x.metric_key === metric.key);
    const row = node("tr"); for (const value of [`${evaluator.evaluator_id} / ${metric.key}`, display(metric), display(after), display(delta)]) row.append(node("td", String(value))); body.append(row);
  }
  table.append(body); wrap.append(table); return wrap;
}
async function showRun() {
  if (!selectedRun || document.activeElement?.closest("#run-detail form")) return;
  const id = selectedRun, r = await api(`/api/runs/${id}`); if (id !== selectedRun || document.activeElement?.closest("#run-detail form")) return;
  const container = $("run-detail"); const fragment = document.createDocumentFragment();
  const intro = node("div", undefined, "detail-intro"); intro.append(node("p", "Run evidence", "eyebrow")); const heading = node("div", undefined, "run-heading"); heading.append(node("h2", `Revision ${r.revision} / ${r.id.slice(0, 8)}`));
  const actions = node("div", undefined, "actions"); actions.append(badge(r.status), node("span", "Assertions:", "hint"), badge(r.assertion_outcome));
  if (["queued", "running"].includes(r.status)) { const cancel = node("button", r.cancel_requested ? "Cancellation requested" : "Cancel run", "danger"); cancel.disabled = Boolean(r.cancel_requested); cancel.onclick = async () => { cancel.disabled = true; try { await api(`/api/runs/${id}/cancel`, {}); await refresh(); } catch(error) { tell(error.message); cancel.disabled = false; } }; actions.append(cancel); }
  else { const retry = node("button", "Rerun effective settings", "secondary"); retry.disabled = Boolean(r.cleanup_pending || r.reconciliation_required); retry.onclick = async () => { retry.disabled = true; try { const overrides = {parameters: {}, unitParameters: Object.fromEntries(r.effective.units.map(u => [u.id,u.parameters])), unitIds: r.effective.units.map(u=>u.id), subjectIds: r.effective.subjects.map(s=>s.id), unitObjectives: Object.fromEntries(r.effective.units.map(u=>[u.id,u.objective])), unitSteering: Object.fromEntries(r.effective.units.map(u=>[u.id,u.steering])), unitConsumerBindings: Object.fromEntries(r.effective.units.filter(u=>u.strategy.startsWith("consumer.")).map(u=>[u.id,u.consumerBinding || r.effective.consumerBinding]))}; const response = await api("/api/runs", {stableId:r.stable_id,revision:r.revision,requestId:retryRequests.get(id) || (retryRequests.set(id,crypto.randomUUID()),retryRequests.get(id)),overrides,retryOf:id}); retryRequests.delete(id); selectedRun=response.runId; await refresh(); } catch(error) { tell(error.message); retry.disabled=false; } }; actions.append(retry); }
  heading.append(actions); intro.append(heading, metadata([`Run ${r.id}`, `Correlation ${r.correlation_id}`, r.error_code || "", r.cleanup_pending ? "Cleanup unconfirmed: execution slot held" : ""]));
  intro.append(details("Immutable effective settings",r.effective), details("Lifecycle events",r.events));
  if (r.reconciliation_required) {
    const form = node("form");
    form.append(node("p", "A remote consumer turn may still be active. Verify that it has stopped before releasing the execution slot.", "hint"));
    const label = node("label", "Reconciliation evidence reference"); label.htmlFor = "reconcile-reference";
    const reference = node("input"); reference.id = "reconcile-reference"; reference.required = true; reference.pattern = "[A-Za-z0-9][A-Za-z0-9._-]{0,95}";
    const confirm = node("button", "Confirm remote stopped", "secondary"); confirm.type = "submit"; confirm.disabled = Boolean(r.cleanup_pending);
    form.append(label, reference, confirm);
    form.onsubmit = async event => { event.preventDefault(); confirm.disabled = true; try { await api(`/api/runs/${id}/reconcile`, {remoteStopped:true,evidenceReference:reference.value}); await refresh(); } catch(error) { tell(error.message); confirm.disabled=false; } };
    intro.append(form);
  }
  fragment.append(intro);
  for(const attempt of r.attempts) { const panel=node("article",undefined,"run-panel"); const unit=r.effective.units.find(u=>u.id===attempt.unit_id), subject=r.effective.subjects.find(s=>s.id===attempt.subject_id); const title=node("div",undefined,"run-heading"); title.append(node("h3",`${unit.title} / ${subject.id}`),badge(attempt.status));panel.append(title,metadata([unit.strategy,`Attempt ${attempt.id}`,attempt.progress ? `Stage: ${attempt.progress.stage}` : "Not started"]));
    const comparison=node("div",undefined,"comparison");for(const [label,text,cls] of [["Subject",subject.text,"prompt"],["Enhanced prompt",attempt.result?.enhanced_prompt ?? "No candidate available.","prompt candidate"]]) { const column=node("div");column.append(node("h3",label),node("div",text,cls));comparison.append(column); }panel.append(comparison);
    if(attempt.result)panel.append(metricsTable(attempt.result),details("Complete result, provider provenance, timings and assertions",attempt.result));
    if(attempt.error_code)panel.append(node("p",attempt.error_code,"hint"));fragment.append(panel);
  }
  const opened=[...container.querySelectorAll("details[open] summary")].map(n=>n.textContent);container.replaceChildren(fragment);for(const d of container.querySelectorAll("details"))d.open=opened.includes(d.querySelector("summary").textContent);
}
async function refresh() { if (refreshBusy) return; refreshBusy=true; try { const [a,b]=await Promise.all([api("/api/experiments"),api("/api/runs")]);experiments=a.experiments;runs=b.runs;if(!selection&&experiments.length){selection=experiments[0];showDefinition();}showExperiments();showRuns();await showRun(); } finally {refreshBusy=false;} }
$("connect-form").onsubmit=async event=>{event.preventDefault();token=$("operator-token").value;try{await refresh();$("operator-token").value="";$("connect").hidden=true;$("workspace").hidden=false;tell("");showDefinition();}catch(error){tell(error.message);token="";}};
$("refresh").onclick=()=>refresh().catch(error=>tell(error.message));
setInterval(()=>{if(token&&!document.hidden)refresh().catch(error=>tell(error.message));},3000);
