<template>
  <q-chip dense :outline="estilo.outline" :color="estilo.color" :text-color="estilo.textColor">
    {{ estilo.label }}
  </q-chip>
</template>

<script setup lang="ts">
import { computed } from 'vue';

export interface EstadoEstilo {
  label: string;
  color: string;
  textColor?: string;
  outline?: boolean;
}

/**
 * Chip de estado de documento, compartido por compras/facturación/cartera/diario.
 * El mapa por defecto cubre los estados comunes; `map` lo extiende o sobreescribe.
 */
const DEFAULT_MAP: Record<string, EstadoEstilo> = {
  DRAFT: { label: 'Borrador', color: 'grey-7', outline: true },
  POSTED: { label: 'Posteado', color: 'secondary', textColor: 'white' },
  ISSUED: { label: 'Emitido', color: 'secondary', textColor: 'white' },
  VOIDED: { label: 'Anulado', color: 'negative', textColor: 'white' },
  PENDING: { label: 'Pendiente', color: 'warning', textColor: 'white' },
  PARTIAL: { label: 'Parcial', color: 'warning', textColor: 'white' },
  PAID: { label: 'Pagado', color: 'secondary', textColor: 'white' },
  OVERDUE: { label: 'Vencido', color: 'negative', textColor: 'white' },
  WRITTEN_OFF: { label: 'Castigado', color: 'grey-9', textColor: 'white' },
  CANCELLED: { label: 'Cancelado', color: 'negative', outline: true },
};

const props = defineProps<{
  estado: string;
  map?: Record<string, EstadoEstilo>;
}>();

const estilo = computed<EstadoEstilo>(
  () =>
    props.map?.[props.estado] ??
    DEFAULT_MAP[props.estado] ?? { label: props.estado, color: 'grey-7', outline: true },
);
</script>
