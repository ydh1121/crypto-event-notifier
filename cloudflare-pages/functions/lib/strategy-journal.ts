/** Read-side pagination of one immutable coin/account revision. */
export type JsonObject = Record<string, any>;
export class JournalError extends Error {
  constructor(public code: string, public status: number) { super(code); }
}
export async function journalPage(
  lab: JsonObject, experimentId: string, revision: string, offset: number, limit: number,
  loadChunk: (strategy: string) => Promise<JsonObject | null>,
): Promise<JsonObject> {
  const account = (Array.isArray(lab.experiments) ? lab.experiments : []).find((e: JsonObject) => e.experiment_id === experimentId);
  if (!account?.journal || !account.revision) throw new JournalError('JOURNAL_UNAVAILABLE', 404);
  if (revision && account.revision !== revision) throw new JournalError('JOURNAL_CHANGED', 409);
  const journal = account.journal;
  if (!journal.complete || !Number.isSafeInteger(journal.total) || journal.total < 0 || !Array.isArray(journal.columns)) throw new JournalError('JOURNAL_INCOMPLETE', 503);
  let values: any[][] = [];
  if (Array.isArray(journal.rows)) {
    if (journal.rows.length !== journal.total) throw new JournalError('JOURNAL_INCOMPLETE', 503);
    values = journal.rows.slice().reverse().slice(offset, offset + limit);
  } else if (Array.isArray(journal.chunks)) {
    if (journal.chunks.reduce((n: number, c: JsonObject) => n + c.count, 0) !== journal.total) throw new JournalError('JOURNAL_INCOMPLETE', 503);
    let skipped = 0;
    for (const ref of [...journal.chunks].reverse()) {
      if (skipped + ref.count <= offset) { skipped += ref.count; continue; }
      if (skipped >= offset + limit) break;
      if (!/^lab-journal:[a-f0-9]{40}$/.test(ref.strategy)) throw new JournalError('JOURNAL_INCOMPLETE', 503);
      const chunk = await loadChunk(ref.strategy);
      if (chunk?.kind !== 'strategy_lab_journal' || chunk?.experiment_id !== experimentId ||
          !Array.isArray(chunk.rows) || chunk.rows.length !== ref.count ||
          JSON.stringify(chunk.columns) !== JSON.stringify(journal.columns)) throw new JournalError('JOURNAL_INCOMPLETE', 503);
      values.push(...chunk.rows.slice().reverse().slice(Math.max(0, offset - skipped), offset + limit - skipped));
      skipped += ref.count;
    }
  } else throw new JournalError('JOURNAL_INCOMPLETE', 503);
  const trades = values.map(row => Object.fromEntries(journal.columns.map((key: string, i: number) => [key, row[i]])));
  const {journal: _rows, ...summary} = account;
  return {account: summary, trades, total: journal.total, offset, limit, revision: account.revision,
    next_offset: offset + trades.length < journal.total ? offset + trades.length : null};
}
export function withoutJournalRows(data: JsonObject): JsonObject {
  if (!data.strategy_lab?.experiments) return data;
  return {...data, strategy_lab: {...data.strategy_lab, experiments: data.strategy_lab.experiments.map((e: JsonObject) => {
    if (!e.journal) return e;
    return {...e, journal: {total: e.journal.total, complete: e.journal.complete}};
  })}};
}
