type JsonPrimitive = string | number | boolean | null;
type JsonValue = JsonPrimitive | undefined | JsonValue[] | { [key: string]: JsonValue };

function toArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  const start = bytes.byteOffset;
  const end = bytes.byteOffset + bytes.byteLength;
  return bytes.buffer.slice(start, end) as ArrayBuffer;
}

function bytesToBase64(bytes: Uint8Array): string {
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function base64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i);
  return out;
}

function sortJson(value: JsonValue): JsonValue {
  if (Array.isArray(value)) return value.map((item) => sortJson(item));
  if (value && typeof value === 'object') {
    const sorted: Record<string, JsonValue> = {};
    for (const key of Object.keys(value).sort()) {
      sorted[key] = sortJson((value as Record<string, JsonValue>)[key]);
    }
    return sorted;
  }
  return value;
}

export function canonJson(value: JsonValue): string {
  return JSON.stringify(sortJson(value));
}

export async function sha256Hex(input: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', toArrayBuffer(input));
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

export async function buildRequestSigningMessage(input: {
  ts: number;
  nonce: string;
  canonicalBodyBytes: Uint8Array;
}): Promise<Uint8Array> {
  const bodyHash = await sha256Hex(input.canonicalBodyBytes);
  return new TextEncoder().encode(`${Math.trunc(input.ts)}.${String(input.nonce)}.${bodyHash}`);
}

export type DeviceKeyPairExport = {
  publicKeyB64: string;
  privateKeyPkcs8B64: string;
};

export async function assertEd25519Supported(): Promise<void> {
  if (!window.isSecureContext || !globalThis.crypto?.subtle) {
    throw new Error('Este flujo requiere HTTPS y WebCrypto (secure context).');
  }
  try {
    const generated = await crypto.subtle.generateKey({ name: 'Ed25519' }, true, ['sign', 'verify']);
    if (!('publicKey' in generated)) throw new Error('No key pair generated');
    await crypto.subtle.exportKey('raw', generated.publicKey);
  } catch {
    throw new Error('Ed25519 no está soportado en este navegador/dispositivo.');
  }
}

export async function generateDeviceEd25519KeyPair(): Promise<DeviceKeyPairExport> {
  await assertEd25519Supported();
  const keyPair = await crypto.subtle.generateKey({ name: 'Ed25519' }, true, ['sign', 'verify']);
  if (!('publicKey' in keyPair)) throw new Error('No key pair generated');
  const publicRaw = new Uint8Array(await crypto.subtle.exportKey('raw', keyPair.publicKey));
  const privatePkcs8 = new Uint8Array(await crypto.subtle.exportKey('pkcs8', keyPair.privateKey));
  return {
    publicKeyB64: bytesToBase64(publicRaw),
    privateKeyPkcs8B64: bytesToBase64(privatePkcs8),
  };
}

export async function signEd25519Pkcs8(privateKeyPkcs8B64: string, message: Uint8Array): Promise<string> {
  await assertEd25519Supported();
  const privateKey = await crypto.subtle.importKey(
    'pkcs8',
    toArrayBuffer(base64ToBytes(privateKeyPkcs8B64)),
    { name: 'Ed25519' },
    false,
    ['sign'],
  );
  const signature = new Uint8Array(await crypto.subtle.sign({ name: 'Ed25519' }, privateKey, toArrayBuffer(message)));
  return bytesToBase64(signature);
}
