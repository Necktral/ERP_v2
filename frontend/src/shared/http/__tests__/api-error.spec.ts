import { describe, expect, it } from 'vitest';

import { extractApiError, extractErrorMessage } from 'src/shared/http/api-error';

describe('extractApiError', () => {
  it('normalizes backend envelope errors', () => {
    const err = {
      isAxiosError: true,
      message: 'Request failed',
      response: {
        status: 403,
        data: {
          error: {
            code: 'RBAC_FORBIDDEN',
            http_status: 403,
            message: 'Acceso denegado.',
            details: { missing_permissions: ['org.branch.read'] },
            request_id: 'abc123',
            timestamp: '2026-03-12T12:00:00Z',
            retryable: false,
          },
        },
      },
    };

    const parsed = extractApiError(err);
    expect(parsed.message).toBe('Acceso denegado.');
    expect(parsed.code).toBe('RBAC_FORBIDDEN');
    expect(parsed.status).toBe(403);
    expect(parsed.requestId).toBe('abc123');
    expect(parsed.retryable).toBe(false);
  });

  it('falls back to legacy detail payloads', () => {
    const err = {
      isAxiosError: true,
      message: 'Request failed',
      response: {
        status: 400,
        data: {
          detail: 'Payload invalido.',
        },
      },
    };

    const parsed = extractApiError(err);
    expect(parsed.message).toBe('Payload invalido.');
    expect(parsed.status).toBe(400);
    expect(parsed.code).toBeNull();
  });

  it('keeps a stable message extraction API', () => {
    const err = {
      isAxiosError: true,
      message: 'Request failed',
      response: {
        status: 500,
        data: {
          error: {
            code: 'INTERNAL_ERROR',
            http_status: 500,
            message: 'Error interno.',
            details: {},
            request_id: 'req-1',
            timestamp: '2026-03-12T12:00:00Z',
            retryable: false,
          },
        },
      },
    };

    expect(extractErrorMessage(err)).toBe('Error interno.');
  });
});
