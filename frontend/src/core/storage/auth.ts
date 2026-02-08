import { STORAGE_KEYS } from './keys';

const AUTH_TRANSPORT = import.meta.env.VITE_AUTH_TRANSPORT || 'header';

export type StoredTokens = {
  access: string | null;
  refresh: string | null;
};

export function readTokens(): StoredTokens {
  if (AUTH_TRANSPORT === 'cookie') {
    return { access: null, refresh: null };
  }
  return {
    access: localStorage.getItem(STORAGE_KEYS.AUTH_ACCESS),
    refresh: localStorage.getItem(STORAGE_KEYS.AUTH_REFRESH),
  };
}

export function writeTokens(tokens: { access: string; refresh: string }) {
  if (AUTH_TRANSPORT === 'cookie') return;
  localStorage.setItem(STORAGE_KEYS.AUTH_ACCESS, tokens.access);
  localStorage.setItem(STORAGE_KEYS.AUTH_REFRESH, tokens.refresh);
}

export function clearTokens() {
  if (AUTH_TRANSPORT === 'cookie') return;
  localStorage.removeItem(STORAGE_KEYS.AUTH_ACCESS);
  localStorage.removeItem(STORAGE_KEYS.AUTH_REFRESH);
}
