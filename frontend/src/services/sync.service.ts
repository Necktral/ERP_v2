import { api } from 'src/boot/axios';

export type EnrollmentChallengeRequest = {
  branch_id?: number | null;
  company_id?: number;
  label_hint?: string;
  expires_in_minutes?: number;
};

export type EnrollmentChallengeResponse = {
  challenge_id: string;
  enrollment_code: string;
  enrollment_uri?: string | null;
  enrollment_deep_link?: string | null;
  expires_at: string;
  company_id: number;
  branch_id: number | null;
};

export type DeviceEnrollRequest = {
  enrollment_code: string;
  public_key_b64: string;
  label?: string;
  meta?: Record<string, unknown>;
};

export type DeviceEnrollResponse = {
  device_id: string;
  device_status: 'ACTIVE' | 'REVOKED' | 'QUARANTINED';
  company_id: number;
  branch_id: number | null;
  server_time: string;
  policy: {
    max_commands_per_batch: number;
    max_payload_bytes: number;
    max_device_clock_skew_seconds: number;
    seq_tolerant: boolean;
  };
};

export type DeviceRow = {
  id: string;
  label: string;
  status: 'ACTIVE' | 'REVOKED' | 'QUARANTINED';
  company_id: number;
  branch_id: number | null;
  created_at: string | null;
  revoked_at: string | null;
  last_seen_at: string | null;
  last_accepted_sequence: number | null;
};

export type DeviceListResponse = {
  count: number;
  limit: number;
  offset: number;
  results: DeviceRow[];
};

export async function createEnrollmentChallenge(payload: EnrollmentChallengeRequest) {
  const { data } = await api.post<EnrollmentChallengeResponse>('/sync/enrollment/challenges/', payload);
  return data;
}

export function resolveEnrollmentQrContent(
  payload: Pick<EnrollmentChallengeResponse, 'enrollment_code' | 'enrollment_uri' | 'enrollment_deep_link'>,
) {
  const uri = typeof payload.enrollment_uri === 'string' ? payload.enrollment_uri.trim() : '';
  const deepLink = typeof payload.enrollment_deep_link === 'string' ? payload.enrollment_deep_link.trim() : '';
  return uri || deepLink || payload.enrollment_code;
}

export async function enrollDevice(payload: DeviceEnrollRequest) {
  const { data } = await api.post<DeviceEnrollResponse>('/sync/enroll/', payload);
  return data;
}

export async function listSyncDevices(params: { q?: string; status?: string; limit?: number; offset?: number } = {}) {
  const { data } = await api.get<DeviceListResponse>('/sync/devices/', { params });
  return data;
}

export async function revokeSyncDevice(deviceId: string) {
  const { data } = await api.post<{ device_id: string; status: 'REVOKED' | 'ACTIVE' | 'QUARANTINED' }>(
    `/sync/devices/${deviceId}/revoke/`,
    {},
  );
  return data;
}
