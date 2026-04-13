import { describe, expect, it } from 'vitest';

import { resolveEnrollmentQrContent } from 'src/services/sync.service';

describe('sync.service enrollment QR', () => {
  it('usa enrollment_uri cuando está disponible', () => {
    const value = resolveEnrollmentQrContent({
      enrollment_code: 'CODE-123',
      enrollment_uri: 'necktral-sync://enroll?code=CODE-123',
    });
    expect(value).toBe('necktral-sync://enroll?code=CODE-123');
  });

  it('hace fallback a enrollment_code cuando no hay enrollment_uri', () => {
    const value = resolveEnrollmentQrContent({
      enrollment_code: 'CODE-456',
      enrollment_uri: '',
    });
    expect(value).toBe('CODE-456');
  });
});
