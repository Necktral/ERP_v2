import { isAxiosError } from 'axios';

export type ApiErrorEnvelope = {
  error: {
    code: string;
    http_status: number;
    message: string;
    details: Record<string, unknown>;
    request_id: string;
    timestamp: string;
    retryable: boolean;
  };
};

export type ApiError = {
  message: string;
  code: string | null;
  status: number | null;
  details: unknown;
  requestId: string | null;
  retryable: boolean | null;
};

type DetailCarrier = { detail?: unknown };

function isRecord(x: unknown): x is Record<string, unknown> {
  return Boolean(x) && typeof x === 'object';
}

function isApiErrorEnvelope(data: unknown): data is ApiErrorEnvelope {
  if (!isRecord(data)) return false;
  const error = data.error;
  if (!isRecord(error)) return false;

  return (
    typeof error.code === 'string' &&
    typeof error.http_status === 'number' &&
    typeof error.message === 'string' &&
    typeof error.request_id === 'string' &&
    typeof error.timestamp === 'string' &&
    typeof error.retryable === 'boolean'
  );
}

function pickLegacyDetail(data: unknown): string | null {
  if (!isRecord(data)) return null;
  const maybe = (data as DetailCarrier).detail;
  return typeof maybe === 'string' ? maybe : null;
}

export function extractApiError(e: unknown): ApiError {
  if (isAxiosError(e)) {
    const status = e.response?.status ?? null;
    const data = e.response?.data;

    if (isApiErrorEnvelope(data)) {
      return {
        message: data.error.message,
        code: data.error.code,
        status: data.error.http_status,
        details: data.error.details,
        requestId: data.error.request_id,
        retryable: data.error.retryable,
      };
    }

    if (typeof data === 'string') {
      return {
        message: data,
        code: null,
        status,
        details: data,
        requestId: null,
        retryable: null,
      };
    }

    const detail = pickLegacyDetail(data);
    if (detail) {
      return {
        message: detail,
        code: null,
        status,
        details: data,
        requestId: null,
        retryable: null,
      };
    }

    return {
      message: e.message || 'Request failed',
      code: null,
      status,
      details: data,
      requestId: null,
      retryable: null,
    };
  }

  if (e instanceof Error) {
    return {
      message: e.message,
      code: null,
      status: null,
      details: null,
      requestId: null,
      retryable: null,
    };
  }

  return {
    message: String(e),
    code: null,
    status: null,
    details: null,
    requestId: null,
    retryable: null,
  };
}

export function extractErrorMessage(e: unknown): string {
  return extractApiError(e).message;
}
