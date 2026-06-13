/**
 * Patrón estándar de listado: rows + loading + reload con notify de error.
 * Sustituye el bloque repetido `loading=true; try{...}catch{notify}finally` de cada página.
 */
import { onMounted, ref, type Ref } from 'vue';
import { Notify } from 'quasar';
import { apiErrorMessage } from 'src/core/api';

export interface ListadoOptions {
  /** Mensaje si el fetch falla y el backend no dio detalle. */
  errorMessage?: string;
  /** Cargar automáticamente al montar (default true). */
  auto?: boolean;
}

export function useListado<T>(
  fetcher: () => Promise<T[]>,
  opts: ListadoOptions = {},
): { rows: Ref<T[]>; loading: Ref<boolean>; reload: () => Promise<void> } {
  const rows = ref<T[]>([]) as Ref<T[]>;
  const loading = ref(false);

  async function reload() {
    loading.value = true;
    try {
      rows.value = await fetcher();
    } catch (e) {
      Notify.create({
        type: 'negative',
        message: apiErrorMessage(e, opts.errorMessage ?? 'No se pudo cargar la información.'),
      });
    } finally {
      loading.value = false;
    }
  }

  if (opts.auto !== false) {
    onMounted(reload);
  }

  return { rows, loading, reload };
}
