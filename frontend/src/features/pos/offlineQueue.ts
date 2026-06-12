import { STORAGE_KEYS } from 'src/core/storage/keys';

const POS_OFFLINE_QUEUE_VERSION = 1;
const POS_OFFLINE_MAX_ATTEMPTS = 8;
const POS_OFFLINE_DONE_KEEP = 50;
const POS_OFFLINE_BACKOFF_CAP_MS = 15 * 60 * 1000;

export type PosOfflineCommandKind = 'CREATE_AND_CHECKOUT' | 'VOID_TICKET' | 'COMPENSATION_RETRY';
export type PosOfflineCommandStatus = 'PENDING' | 'PROCESSING' | 'FAILED' | 'DONE';

export type PosOfflineOpenTicketPayload = {
  shift_id: number;
  idempotency_key?: string;
  external_ref?: string;
  customer_name?: string;
  customer_ref?: string;
  customer_party_id?: number | null;
  sale_type?: string;
  payment_method?: string;
};

export type PosOfflineCheckoutPayload = {
  line?: {
    product?: string;
    volume?: string;
    volume_uom?: string;
    unit_price_entered?: string;
    unit_price_uom?: string;
    amount_estimated?: string;
    metadata?: Record<string, unknown>;
  };
};

export type PosOfflineCreateCheckoutPayload = {
  open_ticket: PosOfflineOpenTicketPayload;
  checkout: PosOfflineCheckoutPayload;
};

export type PosOfflineVoidPayload = {
  ticket_id: number;
  reason?: string;
};

export type PosOfflineCompensationRetryPayload = {
  ticket_id: number;
  reason?: string;
};

export type PosOfflineCommandPayload =
  | PosOfflineCreateCheckoutPayload
  | PosOfflineVoidPayload
  | PosOfflineCompensationRetryPayload;

export type PosOfflineCommand = {
  id: string;
  version: number;
  kind: PosOfflineCommandKind;
  status: PosOfflineCommandStatus;
  company_id: number;
  branch_id: number;
  dedupe_key: string;
  payload: PosOfflineCommandPayload;
  attempts: number;
  created_at: string;
  updated_at: string;
  processed_at: string | null;
  next_retry_at: string | null;
  last_attempt_at: string | null;
  last_error: string;
};

export type PosOfflineQueueStats = {
  total: number;
  pending: number;
  processing: number;
  failed: number;
  done: number;
  due_now: number;
};

export type PosOfflineDrainResult = {
  attempted: number;
  succeeded: number;
  failed: number;
  still_pending: number;
};

type PosOfflineQueueState = {
  version: number;
  commands: PosOfflineCommand[];
};

type PosOfflineDrainOptions = {
  executor: (command: PosOfflineCommand) => Promise<void>;
  nowMs?: number;
  maxCommands?: number;
};

function nowIso(nowMs = Date.now()): string {
  return new Date(nowMs).toISOString();
}

function parseIsoMs(value: string | null | undefined): number {
  if (!value) return 0;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : 0;
}

function nextBackoffMs(attempt: number): number {
  const step = Math.max(1, Math.min(12, attempt));
  return Math.min(2 ** step * 1000, POS_OFFLINE_BACKOFF_CAP_MS);
}

function randomId(): string {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `posq_${Math.random().toString(36).slice(2)}_${Date.now()}`;
}

function safeString(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return fallback;
}

function cloneCommand(raw: PosOfflineCommand): PosOfflineCommand {
  return {
    ...raw,
    payload: JSON.parse(JSON.stringify(raw.payload)) as PosOfflineCommandPayload,
  };
}

function sanitizeStatus(value: unknown): PosOfflineCommandStatus {
  if (value === 'PENDING' || value === 'PROCESSING' || value === 'FAILED' || value === 'DONE') return value;
  return 'PENDING';
}

function sanitizeKind(value: unknown): PosOfflineCommandKind {
  if (value === 'CREATE_AND_CHECKOUT' || value === 'VOID_TICKET' || value === 'COMPENSATION_RETRY') return value;
  return 'CREATE_AND_CHECKOUT';
}

function normalizeCommand(raw: unknown): PosOfflineCommand | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const row = raw as Record<string, unknown>;
  const id = safeString(row.id).trim();
  const dedupeKey = safeString(row.dedupe_key).trim();
  const companyId = Number(row.company_id);
  const branchId = Number(row.branch_id);
  if (!id || !dedupeKey || !Number.isFinite(companyId) || !Number.isFinite(branchId)) return null;

  return {
    id,
    version: Number(row.version) || POS_OFFLINE_QUEUE_VERSION,
    kind: sanitizeKind(row.kind),
    status: sanitizeStatus(row.status),
    company_id: companyId,
    branch_id: branchId,
    dedupe_key: dedupeKey,
    payload: (row.payload ?? {}) as PosOfflineCommandPayload,
    attempts: Math.max(0, Number(row.attempts) || 0),
    created_at: safeString(row.created_at, new Date(0).toISOString()),
    updated_at: safeString(row.updated_at, new Date(0).toISOString()),
    processed_at: row.processed_at ? safeString(row.processed_at) : null,
    next_retry_at: row.next_retry_at ? safeString(row.next_retry_at) : null,
    last_attempt_at: row.last_attempt_at ? safeString(row.last_attempt_at) : null,
    last_error: safeString(row.last_error),
  };
}

function readQueueState(): PosOfflineQueueState {
  const raw = localStorage.getItem(STORAGE_KEYS.POS_OFFLINE_QUEUE);
  if (!raw) return { version: POS_OFFLINE_QUEUE_VERSION, commands: [] };

  try {
    const parsed = JSON.parse(raw) as { version?: number; commands?: unknown[] };
    const commands = Array.isArray(parsed.commands) ? parsed.commands.map(normalizeCommand).filter(Boolean) : [];
    return {
      version: Number(parsed.version) || POS_OFFLINE_QUEUE_VERSION,
      commands: commands as PosOfflineCommand[],
    };
  } catch {
    return { version: POS_OFFLINE_QUEUE_VERSION, commands: [] };
  }
}

function writeQueueState(state: PosOfflineQueueState): void {
  const done = state.commands
    .filter((row) => row.status === 'DONE')
    .sort((a, b) => parseIsoMs(b.processed_at) - parseIsoMs(a.processed_at))
    .slice(0, POS_OFFLINE_DONE_KEEP);
  const active = state.commands.filter((row) => row.status !== 'DONE');
  const compacted = [...active, ...done].sort((a, b) => parseIsoMs(a.created_at) - parseIsoMs(b.created_at));
  localStorage.setItem(
    STORAGE_KEYS.POS_OFFLINE_QUEUE,
    JSON.stringify({
      version: POS_OFFLINE_QUEUE_VERSION,
      commands: compacted,
    }),
  );
}

function updateQueue(mutator: (state: PosOfflineQueueState) => PosOfflineQueueState): PosOfflineQueueState {
  const current = readQueueState();
  const next = mutator(current);
  writeQueueState(next);
  return next;
}

function isRetryableError(error: unknown): { retryable: boolean; message: string } {
  if (typeof error === 'object' && error !== null) {
    const maybe = error as {
      message?: string;
      response?: { status?: number; data?: { error?: { message?: string } } };
      code?: string;
    };
    const status = Number(maybe.response?.status || 0);
    const msg = maybe.response?.data?.error?.message || maybe.message || safeString(maybe.code, 'Unknown error');
    if (!status) return { retryable: true, message: msg };
    if (status >= 500 || status === 429) return { retryable: true, message: msg };
    return { retryable: false, message: msg };
  }
  return { retryable: true, message: String(error) };
}

function isDue(command: PosOfflineCommand, nowMs: number): boolean {
  if (command.status === 'DONE' || command.status === 'PROCESSING') return false;
  const at = parseIsoMs(command.next_retry_at);
  return !at || at <= nowMs;
}

export function listPosOfflineCommands(): PosOfflineCommand[] {
  return readQueueState().commands.map(cloneCommand);
}

export function clearPosOfflineQueue(): void {
  localStorage.removeItem(STORAGE_KEYS.POS_OFFLINE_QUEUE);
}

export function getPosOfflineQueueStats(nowMs = Date.now()): PosOfflineQueueStats {
  const rows = readQueueState().commands;
  let pending = 0;
  let processing = 0;
  let failed = 0;
  let done = 0;
  let dueNow = 0;

  for (const row of rows) {
    if (row.status === 'PENDING') pending += 1;
    else if (row.status === 'PROCESSING') processing += 1;
    else if (row.status === 'FAILED') failed += 1;
    else done += 1;
    if (isDue(row, nowMs)) dueNow += 1;
  }

  return {
    total: rows.length,
    pending,
    processing,
    failed,
    done,
    due_now: dueNow,
  };
}

export function enqueuePosOfflineCommand(input: {
  kind: PosOfflineCommandKind;
  company_id: number;
  branch_id: number;
  dedupe_key: string;
  payload: PosOfflineCommandPayload;
}): { command: PosOfflineCommand; duplicate: boolean } {
  const dedupeKey = String(input.dedupe_key || '').trim();
  if (!dedupeKey) throw new Error('dedupe_key is required for POS offline queue');

  const now = nowIso();
  let result: PosOfflineCommand | null = null;
  let duplicate = false;

  updateQueue((state) => {
    const existing = state.commands.find(
      (row) =>
        row.dedupe_key === dedupeKey &&
        row.company_id === input.company_id &&
        row.branch_id === input.branch_id &&
        row.status !== 'DONE',
    );
    if (existing) {
      duplicate = true;
      result = existing;
      return state;
    }

    const created: PosOfflineCommand = {
      id: randomId(),
      version: POS_OFFLINE_QUEUE_VERSION,
      kind: input.kind,
      status: 'PENDING',
      company_id: Number(input.company_id),
      branch_id: Number(input.branch_id),
      dedupe_key: dedupeKey,
      payload: input.payload,
      attempts: 0,
      created_at: now,
      updated_at: now,
      processed_at: null,
      next_retry_at: null,
      last_attempt_at: null,
      last_error: '',
    };
    result = created;
    return { ...state, commands: [...state.commands, created] };
  });

  if (!result) throw new Error('Could not register POS offline command');
  return { command: cloneCommand(result), duplicate };
}

export async function drainPosOfflineQueue(options: PosOfflineDrainOptions): Promise<PosOfflineDrainResult> {
  const nowMs = Number(options.nowMs || Date.now());
  const maxCommands = Math.max(1, Number(options.maxCommands || 20));
  const due = readQueueState()
    .commands.filter((row) => isDue(row, nowMs))
    .sort((a, b) => parseIsoMs(a.created_at) - parseIsoMs(b.created_at))
    .slice(0, maxCommands);

  let attempted = 0;
  let succeeded = 0;
  let failed = 0;
  let stillPending = 0;

  for (const row of due) {
    attempted += 1;
    updateQueue((state) => ({
      ...state,
      commands: state.commands.map((cmd): PosOfflineCommand =>
        cmd.id === row.id ? { ...cmd, status: 'PROCESSING', updated_at: nowIso() } : cmd,
      ),
    }));

    try {
      await options.executor(cloneCommand(row));
      succeeded += 1;
      updateQueue((state) => ({
        ...state,
        commands: state.commands.map((cmd): PosOfflineCommand =>
          cmd.id === row.id
            ? {
                ...cmd,
                status: 'DONE',
                updated_at: nowIso(),
                processed_at: nowIso(),
                next_retry_at: null,
                last_error: '',
              }
            : cmd,
        ),
      }));
    } catch (error) {
      const verdict = isRetryableError(error);
      const nextAttempts = row.attempts + 1;
      const canRetry = verdict.retryable && nextAttempts < POS_OFFLINE_MAX_ATTEMPTS;
      if (canRetry) stillPending += 1;
      else failed += 1;

      updateQueue((state) => ({
        ...state,
        commands: state.commands.map((cmd): PosOfflineCommand =>
          cmd.id === row.id
            ? {
                ...cmd,
                status: canRetry ? 'PENDING' : 'FAILED',
                attempts: nextAttempts,
                updated_at: nowIso(),
                last_attempt_at: nowIso(),
                last_error: verdict.message.slice(0, 255),
                next_retry_at: canRetry ? nowIso(Date.now() + nextBackoffMs(nextAttempts)) : null,
              }
            : cmd,
        ),
      }));
    }
  }

  return {
    attempted,
    succeeded,
    failed,
    still_pending: stillPending,
  };
}

export function buildCreateCheckoutDedupeKey(params: {
  company_id: number;
  branch_id: number;
  idempotency_key: string;
}): string {
  return `create_checkout:${params.company_id}:${params.branch_id}:${params.idempotency_key}`;
}
