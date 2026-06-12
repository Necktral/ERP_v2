/**
 * Branding configurable por despliegue.
 *
 * La pantalla de login es PREVIA a la autenticación, así que no hay empresa en
 * sesión todavía: la marca del cliente se define por despliegue vía variables de
 * entorno (Vite, prefijo `VITE_`). Necktral es el desarrollador, no la marca del
 * usuario final, por eso va solo como crédito (`developer`).
 *
 * Variables (.env del frontend):
 *   VITE_BRAND_NAME      Nombre del cliente (ej. "Finca La Esperanza")
 *   VITE_BRAND_TAGLINE   Claim corto bajo el nombre
 *   VITE_BRAND_LOGO      URL/ruta del logo (ej. "/brand/logo.svg"); vacío = marca tipográfica
 *   VITE_BRAND_DEVELOPER Crédito del desarrollador (default "Necktral")
 */
const env = import.meta.env as unknown as Record<string, string | undefined>;

function value(key: string, fallback: string): string {
  const raw = env[key];
  return raw && raw.trim() ? raw.trim() : fallback;
}

export interface BrandConfig {
  name: string;
  tagline: string;
  logoUrl: string | null;
  developer: string;
}

const logo = env['VITE_BRAND_LOGO'];

export const BRAND: BrandConfig = {
  name: value('VITE_BRAND_NAME', 'Sistema de Gestión Empresarial'),
  tagline: value('VITE_BRAND_TAGLINE', 'Gestión integrada de tu empresa'),
  logoUrl: logo && logo.trim() ? logo.trim() : null,
  developer: value('VITE_BRAND_DEVELOPER', 'Necktral'),
};
