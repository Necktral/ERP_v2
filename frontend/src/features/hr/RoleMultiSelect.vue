<template>
  <div class="rms">
    <div class="rms-head">
      <span class="rms-count">{{ modelValue.length }} rol(es) seleccionado(s)</span>
      <q-space />
      <q-input
        v-model="search"
        dense
        outlined
        placeholder="Buscar rol…"
        clearable
        class="rms-search"
      >
        <template #prepend><q-icon name="search" /></template>
      </q-input>
    </div>

    <div v-if="loading" class="rms-loading"><q-spinner size="24px" /> Cargando roles…</div>
    <div v-else class="rms-grid">
      <div
        v-for="card in filteredCards"
        :key="card.id"
        class="rms-card"
        :class="{ 'is-selected': isSelected(card.id) }"
      >
        <div class="rms-card__head" @click="toggle(card.id)">
          <q-checkbox :model-value="isSelected(card.id)" dense @update:model-value="toggle(card.id)" />
          <div class="rms-card__title">{{ card.friendly }}</div>
        </div>
        <div class="rms-card__desc">{{ card.blurb }}</div>
        <div class="rms-card__permcount">
          <q-icon name="key" size="14px" /> {{ card.permissions.length }}
          {{ card.permissions.length === 1 ? 'permiso' : 'permisos' }}
        </div>
        <ul class="rms-card__perms">
          <li v-for="p in card.permissions" :key="p.code" class="rms-perm">
            {{ p.description || p.code }}
            <q-tooltip>{{ p.code }}</q-tooltip>
          </li>
          <li v-if="card.permissions.length === 0" class="rms-perm rms-perm--empty">sin permisos</li>
        </ul>
        <div class="rms-card__tag"><q-icon name="admin_panel_settings" size="14px" /> {{ card.name }}</div>
      </div>
    </div>
    <div v-if="!loading && filteredCards.length === 0" class="rms-muted">No hay roles que coincidan.</div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useQuasar } from 'quasar';
import { listRoles, type PermissionRef, type Role } from 'src/features/hr/hr.api';

const props = defineProps<{ modelValue: number[] }>();
const emit = defineEmits<{ (e: 'update:modelValue', v: number[]): void }>();

const $q = useQuasar();
const loading = ref(false);
const search = ref('');
const roles = ref<Role[]>([]);

interface Card {
  id: number;
  name: string;
  friendly: string;
  blurb: string;
  permissions: PermissionRef[];
}

const cards = computed<Card[]>(() =>
  roles.value.map((r) => {
    const d = r.description || '';
    const i = d.indexOf(':');
    return {
      id: r.id,
      name: r.name,
      friendly: i > 0 ? d.slice(0, i).trim() : r.name,
      blurb: i > 0 ? d.slice(i + 1).trim() : d,
      permissions: r.permissions,
    };
  }),
);

const filteredCards = computed(() => {
  const q = search.value.trim().toLowerCase();
  if (!q) return cards.value;
  return cards.value.filter(
    (c) =>
      c.friendly.toLowerCase().includes(q) ||
      c.name.toLowerCase().includes(q) ||
      c.blurb.toLowerCase().includes(q),
  );
});

function isSelected(id: number) {
  return props.modelValue.includes(id);
}

function toggle(id: number) {
  const set = new Set(props.modelValue);
  if (set.has(id)) set.delete(id);
  else set.add(id);
  emit('update:modelValue', [...set]);
}

onMounted(async () => {
  loading.value = true;
  try {
    roles.value = await listRoles();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudieron cargar los roles.' });
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.rms {
  display: flex;
  flex-direction: column;
  gap: var(--app-space-3);
}

.rms-head {
  display: flex;
  align-items: center;
  gap: var(--app-space-3);
}

.rms-count {
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--app-text);
}

.rms-search {
  min-width: 220px;
}

.rms-muted {
  color: var(--app-text-muted);
  padding: var(--app-space-3);
}

.rms-loading {
  display: flex;
  align-items: center;
  gap: var(--app-space-3);
  color: var(--app-text-muted);
  padding: var(--app-space-4);
}

.rms-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: var(--app-space-3);
}

.rms-card {
  display: flex;
  flex-direction: column;
  gap: var(--app-space-1);
  padding: var(--app-space-3) var(--app-space-4);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  background: var(--app-surface);
  color: var(--app-text);
}

.rms-card.is-selected {
  border-color: var(--app-primary);
  box-shadow: var(--app-shadow-card);
}

.rms-card__head {
  display: flex;
  align-items: center;
  gap: var(--app-space-1);
  cursor: pointer;
}

.rms-card__title {
  font-weight: 800;
  font-size: 1rem;
}

.rms-card__desc {
  font-size: 0.76rem;
  color: var(--app-text-muted);
}

.rms-card__permcount {
  font-size: 0.74rem;
  font-weight: 700;
}

.rms-card__perms {
  margin: 0;
  padding: 0 2px;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 120px;
  overflow-y: auto;
}

.rms-perm {
  position: relative;
  padding-left: 12px;
  font-size: 0.72rem;
  line-height: 1.35;
  color: var(--app-text-muted);
}

.rms-perm::before {
  content: '•';
  position: absolute;
  left: 0;
  color: var(--app-secondary);
}

.rms-perm--empty {
  font-style: italic;
}

.rms-perm--empty::before {
  content: '';
}

.rms-card__tag {
  margin-top: var(--app-space-1);
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--app-primary);
}
</style>
