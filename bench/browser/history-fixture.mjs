export function historyResponse(runs, query, comparisons = { groups: [], truncated: false, groupLimit: 200 }) {
  const filtered = runs.filter(run => [
    ['status', 'status'], ['experiment', 'stable_id'], ['revision', 'revision'], ['origin', 'origin'], ['model', 'model'],
  ].every(([param, key]) => !query.get(param) || query.get(param) === run[key])
    && (!query.get('fromDate') || run.created >= Date.parse(query.get('fromDate')) / 1000)
    && (!query.get('toDate') || run.created < Date.parse(query.get('toDate')) / 1000 + 86400));
  const cursor = query.get('before'), start = cursor ? filtered.findIndex(run => run.id === cursor) + 1 : 0;
  const end = start + Number(query.get('limit') || 100), visible = filtered.slice(start, end);
  return {
    runs: visible, nextCursor: end < filtered.length ? visible.at(-1).id : null,
    modelOptions: ['example-model-a', 'example-model-b'],
    summary: {
      total: filtered.length, plannedAttempts: filtered.length * 4,
      statuses: ['queued', 'running', 'succeeded', 'failed', 'cancelled', 'interrupted', 'superseded'].map(status => ({ status, count: filtered.filter(run => run.status === status).length })),
      activityFrom: '2026-10-10', activityTo: '2026-10-11',
      activity: [{ day: '2026-10-10', count: filtered.length }, { day: '2026-10-11', count: 0 }],
      comparisons: filtered.length ? comparisons : { groups: [] },
    },
  };
}
