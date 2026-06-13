<template>
  <q-select
    :model-value="modelValue"
    :options="opciones"
    :label="label ?? 'Tercero'"
    outlined
    dense
    use-input
    clearable
    emit-value
    map-options
    input-debounce="350"
    :loading="buscando"
    @update:model-value="onSelect"
    @filter="filtrar"
  >
    <template #option="scope">
      <q-item v-bind="scope.itemProps">
        <q-item-section>
          <q-item-label>{{ scope.opt.label }}</q-item-label>
          <q-item-label caption>{{ scope.opt.caption }}</q-item-label>
        </q-item-section>
      </q-item>
    </template>
    <template #no-option>
      <q-item>
        <q-item-section class="text-muted">Sin coincidencias. Escribí para buscar.</q-item-section>
      </q-item>
    </template>
  </q-select>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import {
  listParties,
  PARTY_ROLE_LABELS,
  type Party,
  type PartyRoleCode,
} from 'src/features/parties/parties.api';

const props = defineProps<{
  modelValue: number | null;
  /** Limita la búsqueda a terceros con este rol activo (ej. SUPPLIER en compras). */
  role?: PartyRoleCode;
  label?: string;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: number | null];
  /** El objeto completo del tercero elegido (o null al limpiar). */
  selected: [party: Party | null];
}>();

interface Opcion {
  label: string;
  value: number;
  caption: string;
}

const opciones = ref<Opcion[]>([]);
const buscando = ref(false);
const porId = new Map<number, Party>();

function aOpcion(p: Party): Opcion {
  const partes = [
    p.tax_id ? `RUC ${p.tax_id}` : p.national_id ? `Cédula ${p.national_id}` : '',
    p.roles.map((r) => PARTY_ROLE_LABELS[r]).join(', '),
  ].filter(Boolean);
  return { label: p.display_name, value: p.id, caption: partes.join(' · ') };
}

function filtrar(input: string, update: (fn: () => void) => void, abort: () => void) {
  buscando.value = true;
  listParties({ q: input.trim(), role: props.role ?? '', status: 'ACTIVE' })
    .then((rows) => {
      update(() => {
        porId.clear();
        for (const p of rows) porId.set(p.id, p);
        opciones.value = rows.map(aOpcion);
      });
    })
    .catch(() => abort())
    .finally(() => {
      buscando.value = false;
    });
}

function onSelect(value: number | null) {
  emit('update:modelValue', value);
  emit('selected', value != null ? (porId.get(value) ?? null) : null);
}
</script>
