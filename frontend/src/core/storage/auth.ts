import { STORAGE_KEYS } from './keys';

export type StoredTokens = {
  access: string | null;
  refresh: string | null;
};

export function readTokens(): StoredTokens {
  return { access: null, refresh: null };
}

export function writeTokens() {
  // No-op: el frontend usa cookies HttpOnly (no almacena JWT en storage).
}

export function clearTokens() {
  // Limpia residuos de sesiones legacy basadas en storage.
  localStorage.removeItem(STORAGE_KEYS.AUTH_ACCESS);
  localStorage.removeItem(STORAGE_KEYS.AUTH_REFRESH);
}
