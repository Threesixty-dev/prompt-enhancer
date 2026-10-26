export function historyResponse(runs, query, comparisons = { groups: [], truncated: false, groupLimit: 200 }) {
  const filtered = runs.filter(run => [
    ['status', 'status'], ['experiment', 'stable_id'], ['revision', 'revision'], ['origin', 'origin'], ['model', 'model'],
  ].every(([param, key]) => !query.get(param) || query.get(param) === run[key])
    && (!query.get('fromDate') || run.created >= Date.parse(query.get('fromDate')) / 1000)
    && (!query.get('toDate') || run.created < Date.parse(query.get('toDate')) / 1000 + 86400));
  const cursor = query.get('before'), start = cursor ? filtered.findIndex(run => run.id === cursor) + 1 : 0;
  const end = start + Number(query.get('limit') || 100), visible = filtered.slice(start, end);
  const groups = new Map();
  for (const run of filtered) {
    if (!groups.has(run.stable_id)) groups.set(run.stable_id, { stableId: run.stable_id, runCount: 0, queuedRuns: 0, runningRuns: 0, finished: 0, total: 0 });
    const group = groups.get(run.stable_id);
    group.runCount++;
    if (run.status === 'queued') group.queuedRuns++;
    if (run.status === 'running') group.runningRuns++;
    if (run.attemptProgress && group.total !== null) {
      group.finished += run.attemptProgress.finished;
      group.total += run.attemptProgress.total;
    } else group.finished = group.total = null;
  }
  return {
    runs: visible, nextCursor: end < filtered.length ? visible.at(-1).id : null,
    modelOptions: ['example-model-a', 'example-model-b'],
    summary: {
      total: filtered.length, plannedAttempts: filtered.length * 4,
      experimentProgress: [...groups.values()],
      statuses: ['queued', 'running', 'succeeded', 'failed', 'cancelled', 'interrupted', 'superseded'].map(status => ({ status, count: filtered.filter(run => run.status === status).length })),
      activityFrom: '2026-10-10', activityTo: '2026-10-11',
      activity: [{ day: '2026-10-10', count: filtered.length }, { day: '2026-10-11', count: 0 }],
      comparisons: filtered.length ? comparisons : { groups: [] },
    },
  };
}
