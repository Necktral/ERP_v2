import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  buildCreateCheckoutDedupeKey,
  clearPosOfflineQueue,
  drainPosOfflineQueue,
  enqueuePosOfflineCommand,
  getPosOfflineQueueStats,
  listPosOfflineCommands,
} from 'src/features/pos/offlineQueue';

describe('pos offline queue', () => {
  beforeEach(() => {
    localStorage.clear();
    clearPosOfflineQueue();
  });

  it('avoids duplicates by active dedupe_key', () => {
    const dedupe = buildCreateCheckoutDedupeKey({
      company_id: 10,
      branch_id: 20,
      idempotency_key: 'ticket-001',
    });

    const first = enqueuePosOfflineCommand({
      kind: 'CREATE_AND_CHECKOUT',
      company_id: 10,
      branch_id: 20,
      dedupe_key: dedupe,
      payload: {
        open_ticket: { shift_id: 3, idempotency_key: 'ticket-001' },
        checkout: {},
      },
    });
    const second = enqueuePosOfflineCommand({
      kind: 'CREATE_AND_CHECKOUT',
      company_id: 10,
      branch_id: 20,
      dedupe_key: dedupe,
      payload: {
        open_ticket: { shift_id: 3, idempotency_key: 'ticket-001' },
        checkout: {},
      },
    });

    expect(first.duplicate).toBe(false);
    expect(second.duplicate).toBe(true);
    expect(second.command.id).toBe(first.command.id);
    expect(listPosOfflineCommands()).toHaveLength(1);
  });

  it('drains queue and marks commands as DONE after executor success', async () => {
    const dedupe = buildCreateCheckoutDedupeKey({
      company_id: 11,
      branch_id: 21,
      idempotency_key: 'ticket-002',
    });
    enqueuePosOfflineCommand({
      kind: 'CREATE_AND_CHECKOUT',
      company_id: 11,
      branch_id: 21,
      dedupe_key: dedupe,
      payload: {
        open_ticket: { shift_id: 4, idempotency_key: 'ticket-002' },
        checkout: {},
      },
    });

    const executor = vi.fn(async () => {});
    const result = await drainPosOfflineQueue({ executor, maxCommands: 5 });
    expect(executor).toHaveBeenCalledTimes(1);
    expect(result.succeeded).toBe(1);

    const rows = listPosOfflineCommands();
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      status: 'DONE',
      next_retry_at: null,
      last_error: '',
    });
    expect(rows[0]?.processed_at).not.toBeNull();
  });

  it('retries transient errors with backoff and keeps command pending', async () => {
    const dedupe = buildCreateCheckoutDedupeKey({
      company_id: 12,
      branch_id: 22,
      idempotency_key: 'ticket-003',
    });
    enqueuePosOfflineCommand({
      kind: 'CREATE_AND_CHECKOUT',
      company_id: 12,
      branch_id: 22,
      dedupe_key: dedupe,
      payload: {
        open_ticket: { shift_id: 5, idempotency_key: 'ticket-003' },
        checkout: {},
      },
    });

    const executor = vi.fn(() => Promise.reject(new Error('gateway timeout')));

    const result = await drainPosOfflineQueue({ executor, maxCommands: 5 });
    expect(result.succeeded).toBe(0);
    expect(result.failed).toBe(0);
    expect(result.still_pending).toBe(1);

    const rows = listPosOfflineCommands();
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      status: 'PENDING',
      attempts: 1,
    });
    expect(rows[0]?.next_retry_at).not.toBeNull();

    const stats = getPosOfflineQueueStats();
    expect(stats.pending).toBe(1);
    expect(stats.done).toBe(0);
  });
});
