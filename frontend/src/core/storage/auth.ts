import { STORAGE_KEYS } from './keys';

export type StoredTokens = {
  access: string | null;
  refresh: string | null;
};

export function readTokens(): StoredTokens {
  return {
    access: localStorage.getItem(STORAGE_KEYS.AUTH_ACCESS),
    refresh: localStorage.getItem(STORAGE_KEYS.AUTH_REFRESH),
  };
}

export function writeTokens(tokens: { access: string; refresh: string }) {
  localStorage.setItem(STORAGE_KEYS.AUTH_ACCESS, tokens.access);
  localStorage.setItem(STORAGE_KEYS.AUTH_REFRESH, tokens.refresh);
}

export function clearTokens() {
  localStorage.removeItem(STORAGE_KEYS.AUTH_ACCESS);
  localStorage.removeItem(STORAGE_KEYS.AUTH_REFRESH);
}
