/**
 * Identidad del dispositivo enrolado — fuente única.
 *
 * Flujo (sync_engine): un usuario con permiso genera un código de un solo uso
 * (web → Dispositivos); este aparato manda código + clave pública Ed25519 a
 * `/sync/enroll/` y recibe su `device_id`. La clave privada NUNCA sale del
 * aparato: servirá para FIRMAR los lotes offline del canal de sync.
 *
 * Todo request del aparato lleva `X-Device-Id` (lo agrega el boot de axios);
 * la auditoría solo lo registra si corresponde a un Device ACTIVO de la empresa.
 */
import nacl from 'tweetnacl';
import { api } from 'src/boot/axios';

const STORAGE_KEY = 'nt_device_identity';

export interface DeviceIdentity {
  device_id: string;
  label: string;
  public_key_b64: string;
  secret_key_b64: string; // privada: solo vive en este aparato
  enrolled_at: string;
}

function toB64(bytes: Uint8Array): string {
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

export function getDeviceIdentity(): DeviceIdentity | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as DeviceIdentity;
    return parsed.device_id ? parsed : null;
  } catch {
    return null;
  }
}

export function isEnrolled(): boolean {
  return getDeviceIdentity() !== null;
}

export async function enrollDevice(enrollmentCode: string, label: string): Promise<DeviceIdentity> {
  const keys = nacl.sign.keyPair(); // Ed25519: publicKey 32 bytes
  const { data } = await api.post<{ device_id: string }>(
    '/sync/enroll/',
    {
      enrollment_code: enrollmentCode.trim(),
      public_key_b64: toB64(keys.publicKey),
      label: label.trim(),
    },
    { _skipAuthRefresh: true },
  );
  const identity: DeviceIdentity = {
    device_id: data.device_id,
    label: label.trim(),
    public_key_b64: toB64(keys.publicKey),
    secret_key_b64: toB64(keys.secretKey),
    enrolled_at: new Date().toISOString(),
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(identity));
  return identity;
}

/** Olvida la identidad LOCAL (la revocación del lado servidor va aparte). */
export function forgetDevice(): void {
  localStorage.removeItem(STORAGE_KEY);
}
