import { node } from './forms.js';

const stages = { evaluate_original: 'Evaluating the original prompt', evaluate_candidate: 'Evaluating the enhanced prompt',
  generate: 'Generating or reviewing the prompt', finished: 'Finished' };
const hints = {
  gateway_io_timeout: 'The gateway response timed out after connection. The remote request may have finished; its completion was not confirmed.',
  gateway_connect_timeout: 'The connection to the gateway timed out.',
  gateway_connect_failed: 'The connection to the gateway failed.',
  gateway_io_failed: 'The gateway connection was lost during the request or response.',
  gateway_tls_failed: 'The secure connection could not be verified. Check the configured certificate trust.',
  gateway_http_unauthorized: 'The contacted service rejected the credential. Check the configured key.',
  gateway_http_forbidden: 'The contacted service denied access. Check the configured permissions.',
  gateway_http_rate_limited: 'The contacted service reported a limit. Check its budget and rate limits.',
  gateway_http_server_error: 'The contacted service returned a server error. Remote completion may be unconfirmed.',
  workflow_review_reply_invalid: 'The model reply did not satisfy the review contract. Inspect the recorded validation details.',
  container_cleanup_unconfirmed: 'Bench could not confirm removal of its core container. The execution slot is held.',
  run_deadline_exceeded: 'The whole-run time limit was reached. Use smaller batches after recovery.',
  worker_restarted_no_replay: 'The worker restarted while this run was active. The interrupted work was preserved.',
};
const at = value => typeof value === 'number' ? new Date(value * 1000).toLocaleString() : 'Not recorded';
const text = (label, value) => {
  const row = node('p'); row.append(node('strong', label + ': '), node('span', value ?? 'Unknown')); return row;
};

export function failurePanel(failure) {
  if (!failure) return null;
  const box = node('section', undefined, 'execution-issue'); box.setAttribute('aria-label', 'Execution issue');
  box.append(node('h2', 'Execution issue'), text('Cause', failure.code),
    text('Stage', stages[failure.stage] || failure.stage || 'Not recorded'));
  if (hints[failure.code]) box.append(node('p', hints[failure.code]));
  if (failure.subjectId) box.append(text('Case / variant', failure.subjectId + ' / ' + failure.unitId));
  box.append(node('p', 'Completed results are retained. Unavailable measurements remain unknown; this error is separate from quality assertions.', 'hint'));
  return box;
}

export function recoveryBanner(value, runPath, link) {
  const box = document.createDocumentFragment();
  if (!value.blocked) return box;
  box.append(node('h2', 'Queue paused: recovery required'),
    node('p', 'New runs can be queued, but execution is waiting for ' + value.total + ' blocked run(s). This applies across experiments and filters.'));
  const list = node('ul');
  for (const run of value.runs) {
    const item = node('li'); item.append(link('Open blocked run ' + run.id.slice(0, 8), runPath(run)),
      node('span', ' - ' + (run.failure?.code || run.error_code || 'Cause not recorded') +
        (run.failure?.stage ? ' / ' + run.failure.stage : ''))); list.append(item);
  }
  box.append(list);
  if (value.truncated) box.append(node('p', 'Showing the oldest 100 blocked runs. More remain.', 'hint'));
  return box;
}

export function recoveryPanel(run, api, refresh, tell) {
  const recovery = run.recovery;
  if (!run.cleanup_pending && !run.reconciliation_required && !recovery?.reconciliation && !recovery?.cleanupCheck) return null;
  if (['queued', 'running'].includes(run.status)) return null;
  const box = node('section', undefined, 'recovery-panel'); box.setAttribute('aria-label', 'Run recovery');
  box.append(node('h2', run.cleanup_pending || run.reconciliation_required ? 'Recovery required' : 'Recovery recorded'),
    text('Local container', run.cleanup_pending ? 'Cleanup unconfirmed' : 'Cleanup confirmed'),
    text('Remote operation', run.reconciliation_required ? 'Completion unconfirmed' : recovery?.reconciliation ? 'Stopped - operator confirmed' : 'No remote recovery hold recorded'),
    node('p', 'Recovery preserves this run and its errors. It never replays the interrupted attempt. Releasing the hold allows already queued runs to start.', 'hint'));
  const check = recovery?.cleanupCheck;
  if (check) {
    box.append(text('Last cleanup check', at(check.checked_at)), text('Cleanup checks in this cycle', check.attempts + ' / 3'));
    if (check.error_code) box.append(text('Cleanup error', check.error_code));
  }
  if (run.cleanup_pending) {
    if (recovery?.nextAction === 'retry_cleanup') {
      box.append(node('p', 'Automatic cleanup checks stopped. Resolve the Docker or ownership error, then request another bounded check cycle.'));
      const retry = node('button', 'Retry container cleanup', 'secondary'); retry.type = 'button';
      retry.onclick = async () => {
        retry.disabled = true;
        try { await api('/api/runs/' + encodeURIComponent(run.id) + '/cleanup-check', {}); await refresh(); }
        catch (error) { tell(error.message); retry.disabled = false; }
      }; box.append(retry);
    } else box.append(node('p', check?.next_check ? 'Next cleanup check: ' + at(check.next_check) + '. The worker must be available.'
      : 'Container cleanup is pending. The worker will check it when available.', 'hint'));
  }
  if (run.reconciliation_required) {
    box.append(text('Request reference', run.failure?.operationId || 'Not recorded - automatic remote verification unavailable'),
      text('Run started', at(run.started)), text('Interruption recorded', at(run.finished)),
      node('p', 'Next: confirm completion or cancellation of the affected request on its model host. A healthy service, elapsed time, or a later successful request does not establish this request\'s completion.'));
    const form = node('form'); form.append(node('p', 'Verify that all remote consumer and evaluator operations have stopped before releasing the execution slot.', 'hint'));
    const label = node('label', 'Reconciliation evidence reference'); label.htmlFor = 'reconcile-reference';
    const reference = node('input'); reference.id = 'reconcile-reference'; reference.required = true; reference.maxLength = 96;
    reference.pattern = '[A-Za-z0-9][A-Za-z0-9._-]{0,95}'; reference.autocomplete = 'off';
    const help = node('p', 'Use a short check or ticket ID. Keep credentials, prompts and raw logs out of this field.', 'hint');
    help.id = 'reconcile-help'; reference.setAttribute('aria-describedby', help.id);
    const checked = node('input'); checked.type = 'checkbox'; checked.required = true;
    const acknowledgement = node('label', undefined, 'check-option');
    acknowledgement.append(checked, node('span', 'I verified that the affected remote operations finished or stopped.'));
    const confirm = node('button', 'Confirm remote stopped', 'secondary'); confirm.type = 'submit'; confirm.disabled = Boolean(run.cleanup_pending);
    form.append(label, reference, help, acknowledgement, confirm);
    form.onsubmit = async event => {
      event.preventDefault(); confirm.disabled = true;
      try { await api('/api/runs/' + encodeURIComponent(run.id) + '/reconcile', { remoteStopped: true, evidenceReference: reference.value }); confirm.blur(); await refresh(); }
      catch (error) { tell(error.message); confirm.disabled = false; }
    }; box.append(form);
  } else if (recovery?.reconciliation) box.append(text('Stop evidence reference', recovery.reconciliation.evidence_reference),
    text('Confirmed at', at(recovery.reconciliation.created)));
  return box;
}
