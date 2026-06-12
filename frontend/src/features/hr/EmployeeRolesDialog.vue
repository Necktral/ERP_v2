<template>
  <q-dialog v-model="open">
    <q-card class="erd">
      <q-card-section>
        <div class="text-h6">Roles del trabajador</div>
        <div class="text-caption erd-muted">{{ employeeName }}</div>
      </q-card-section>

      <q-card-section class="erd-body">
        <div v-if="loading" class="erd-loading"><q-spinner size="28px" /> Cargando…</div>
        <RoleMultiSelect v-else v-model="selectedIds" />
      </q-card-section>

      <q-card-actions class="erd-foot">
        <q-space />
        <q-btn flat label="Cancelar" @click="open = false" />
        <q-btn unelevated color="primary" label="Guardar roles" :loading="saving" @click="save" />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useQuasar } from 'quasar';
import { getEmployeeRoles, setEmployeeRoles } from 'src/features/hr/hr.api';
import RoleMultiSelect from 'src/features/hr/RoleMultiSelect.vue';

const props = defineProps<{
  modelValue: boolean;
  employeeId: number | null;
  employeeName: string;
}>();
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void;
  (e: 'saved'): void;
}>();

const $q = useQuasar();

const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
});

const loading = ref(false);
const saving = ref(false);
const selectedIds = ref<number[]>([]);

async function load() {
  if (props.employeeId == null) return;
  loading.value = true;
  selectedIds.value = [];
  try {
    const current = await getEmployeeRoles(props.employeeId);
    selectedIds.value = current.map((m) => m.role_id);
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudieron cargar los roles.' });
  } finally {
    loading.value = false;
  }
}

async function save() {
  if (props.employeeId == null) return;
  saving.value = true;
  try {
    await setEmployeeRoles(props.employeeId, selectedIds.value);
    $q.notify({ type: 'positive', message: 'Roles del trabajador actualizados.' });
    emit('saved');
    open.value = false;
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudieron guardar los roles.' });
  } finally {
    saving.value = false;
  }
}

watch(
  () => [props.modelValue, props.employeeId],
  ([isOpen]) => {
    if (isOpen) void load();
  },
);
</script>

<style scoped>
.erd {
  width: 820px;
  max-width: 95vw;
  background: var(--app-surface-strong);
}

.erd-muted {
  color: var(--app-text-muted);
}

.erd-body {
  max-height: 68vh;
  overflow: auto;
}

.erd-loading {
  display: flex;
  align-items: center;
  gap: var(--app-space-3);
  color: var(--app-text-muted);
  padding: var(--app-space-4);
}

.erd-foot {
  border-top: 1px solid var(--app-border);
  padding: var(--app-space-3) var(--app-space-4);
}
</style>
