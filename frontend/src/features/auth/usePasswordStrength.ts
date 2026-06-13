import { computed, type Ref } from 'vue';
import { api } from 'src/boot/axios';

/**
 * Medidor de fortaleza de contraseña alineado a la política REAL del backend.
 *
 * La política es la fuente única (`GET /auth/bootstrap/status/` → `password_policy`,
 * derivada de `AUTH_PASSWORD_VALIDATORS`). NO hardcodear los niveles: el componente
 * debe consumirla para no desincronizarse de lo que el backend exige.
 * Colores por tokens de Quasar (`negative/warning/positive`) para respetar multi-tema.
 */
export interface PasswordPolicy {
  min_length: number;
  min_classes: number;
  classes: string[];
  disallow_common: boolean;
  disallow_numeric_only: boolean;
}

export const DEFAULT_PASSWORD_POLICY: PasswordPolicy = {
  min_length: 10,
  min_classes: 3,
  classes: ['minúsculas', 'mayúsculas', 'números', 'símbolos'],
  disallow_common: true,
  disallow_numeric_only: true,
};

export interface PasswordCheck {
  key: string;
  label: string;
  ok: boolean;
}

export interface PasswordStrength {
  ratio: number;
  color: string;
  label: string;
  icon: string;
  meetsPolicy: boolean;
}

/** Trae la política real del backend; null si no se pudo (se usan los defaults). */
export async function fetchPasswordPolicy(): Promise<PasswordPolicy | null> {
  try {
    const { data } = await api.get<{ password_policy?: PasswordPolicy }>('/auth/bootstrap/status/');
    return data.password_policy ?? null;
  } catch {
    return null;
  }
}

const CLASS_KEYS = ['lower', 'upper', 'digit', 'symbol'];

export function usePasswordStrength(password: Ref<string>, policy: Ref<PasswordPolicy>) {
  const hint = computed(
    () =>
      `Mínimo ${policy.value.min_length} caracteres y al menos ` +
      `${policy.value.min_classes} de: minúsculas, mayúsculas, números, símbolos.`,
  );

  const checks = computed<PasswordCheck[]>(() => {
    const p = password.value;
    return [
      {
        key: 'len',
        label: `${policy.value.min_length}+ caracteres`,
        ok: p.length >= policy.value.min_length,
      },
      { key: 'lower', label: 'minúscula', ok: /[a-z]/.test(p) },
      { key: 'upper', label: 'mayúscula', ok: /[A-Z]/.test(p) },
      { key: 'digit', label: 'número', ok: /[0-9]/.test(p) },
      { key: 'symbol', label: 'símbolo', ok: /[^A-Za-z0-9]/.test(p) },
    ];
  });

  const strength = computed<PasswordStrength>(() => {
    const p = password.value;
    const classesMet = checks.value.filter((c) => CLASS_KEYS.includes(c.key) && c.ok).length;
    const lengthOk = p.length >= policy.value.min_length;
    const meetsPolicy = lengthOk && classesMet >= policy.value.min_classes;

    // score 0..5 (longitud + nº de clases) → degradado rojo→amarillo→verde
    const score = (lengthOk ? 1 : 0) + classesMet;
    const ratio = Math.min(score / 5, 1);

    let color = 'negative';
    let label = 'Débil';
    let icon = 'gpp_bad';
    if (meetsPolicy && score >= 5) {
      color = 'positive';
      label = 'Excelente';
      icon = 'verified_user';
    } else if (meetsPolicy) {
      color = 'positive';
      label = 'Buena';
      icon = 'gpp_good';
    } else if (score >= 3) {
      color = 'warning';
      label = 'Media';
      icon = 'gpp_maybe';
    }

    return { ratio, color, label, icon, meetsPolicy };
  });

  return { hint, checks, strength };
}
