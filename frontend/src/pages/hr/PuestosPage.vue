<template>
  <q-page class="app-page">
    <PageHeader
      title="Puestos"
      subtitle="Cada puesto define qué puede hacer la persona. Se configura una vez y se reutiliza."
      :loading="loading"
      @refresh="reload"
    />

    <div class="app-actions">
      <button type="button" class="hr-picker-trigger" @click="openPicker">
        <q-icon name="add" size="20px" />
        <span class="hr-picker-trigger__label">Elegir puesto…</span>
        <q-icon name="expand_more" size="20px" class="hr-picker-trigger__chev" />
      </button>
      <span class="text-caption text-muted">
        Cada puesto trae sus permisos precargados. También podés crear uno personalizado.
      </span>
    </div>

    <q-table
      class="app-table"
      :rows="positions"
      :columns="columns"
      row-key="id"
      flat
      :loading="loading"
      :pagination="{ rowsPerPage: 25 }"
      no-data-label="Aún no hay puestos. Usa «Elegir puesto»."
    >
      <template #body-cell-estado="props">
        <q-td :props="props">
          <q-chip v-if="props.row.is_active" dense color="secondary" text-color="white">Activo</q-chip>
          <q-chip v-else dense outline color="grey-7">Inactivo</q-chip>
        </q-td>
      </template>
      <template #body-cell-acciones="props">
        <q-td :props="props" class="text-right">
          <q-btn
            flat
            dense
            no-caps
            size="sm"
            icon="admin_panel_settings"
            label="Roles"
            @click="openRoles(props.row)"
          />
        </q-td>
      </template>
    </q-table>

    <!-- Picker: cartas de puesto/rol -->
    <q-dialog v-model="pickerDialog">
      <q-card class="hr-picker">
        <q-card-section class="row items-center no-wrap q-gutter-md">
          <div class="text-h6">Elegir puesto</div>
          <q-space />
          <q-input
            v-model="pickerSearch"
            dense
            outlined
            placeholder="Buscar puesto o rol…"
            clearable
            class="hr-picker__search"
          >
            <template #prepend><q-icon name="search" /></template>
          </q-input>
        </q-card-section>

        <q-card-section class="hr-picker__body">
          <div class="hr-card-grid">
            <div v-for="card in filteredRoleCards" :key="card.id" class="hr-rolecard">
              <div class="hr-rolecard__title">{{ card.friendly }}</div>
              <div class="hr-rolecard__desc">{{ card.blurb }}</div>
              <div class="hr-rolecard__permcount">
                <q-icon name="key" size="14px" />
                {{ card.permissions.length }}
                {{ card.permissions.length === 1 ? 'permiso' : 'permisos' }}
              </div>
              <ul class="hr-rolecard__perms">
                <li v-for="p in card.permissions" :key="p.code" class="hr-perm-item">
                  {{ p.description || p.code }}
                  <q-tooltip>{{ p.code }}</q-tooltip>
                </li>
                <li v-if="card.permissions.length === 0" class="hr-perm-empty">sin permisos</li>
              </ul>
              <div class="hr-rolecard__foot">
                <span class="hr-rolecard__tag">
                  <q-icon name="admin_panel_settings" size="14px" />
                  {{ card.name }}
                </span>
                <q-btn
                  dense
                  no-caps
                  unelevated
                  color="primary"
                  icon="add"
                  label="Usar"
                  :loading="saving"
                  @click="createFromRole(card)"
                />
              </div>
            </div>
          </div>
          <div v-if="filteredRoleCards.length === 0" class="text-caption text-muted q-pa-md">
            No hay roles que coincidan.
          </div>

          <q-separator spaced />
          <div class="hr-custom">
            <q-input
              v-model="customName"
              dense
              outlined
              label="¿Otro puesto? Créalo con nombre libre (sin rol; lo mapeas luego)"
              @keyup.enter="createCustom"
            />
            <q-btn
              flat
              no-caps
              icon="add"
              label="Crear"
              :disable="!customName.trim() || saving"
              @click="createCustom"
            />
          </div>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- Diálogo: ajustar roles de un puesto existente -->
    <q-dialog v-model="rolesDialog">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Roles de "{{ rolesTarget?.name }}"</q-card-section>
        <q-card-section>
          <div class="text-caption text-muted q-mb-sm">
            Define qué roles otorga este puesto. <strong>Reemplaza</strong> el mapeo anterior.
            <em>Sucursal</em> = aplica en la sucursal de la asignación; <em>Empresa</em> = a toda la
            empresa.
          </div>
          <div v-for="(row, idx) in roleRows" :key="idx" class="hr-rolerow">
            <q-select
              v-model="row.role_id"
              :options="roleOptions"
              label="Rol"
              outlined
              dense
              emit-value
              map-options
              class="col"
            >
              <template #option="scope">
                <q-item v-bind="scope.itemProps">
                  <q-item-section>
                    <q-item-label>{{ scope.opt.label }}</q-item-label>
                    <q-item-label caption lines="2">{{ scope.opt.description }}</q-item-label>
                  </q-item-section>
                </q-item>
              </template>
            </q-select>
            <q-btn-toggle
              v-model="row.scope_mode"
              dense
              no-caps
              unelevated
              :options="[
                { label: 'Sucursal', value: 'BRANCH' },
                { label: 'Empresa', value: 'COMPANY' },
              ]"
            />
            <q-btn flat dense round icon="delete" color="grey-7" @click="roleRows.splice(idx, 1)" />
          </div>
          <q-btn flat dense no-caps icon="add" label="Agregar rol" @click="addRoleRow" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Cancelar" v-close-popup />
          <q-btn unelevated color="primary" label="Guardar roles" :loading="saving" @click="saveRoles" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import {
  createPosition,
  getPositionRoles,
  listPositions,
  listRoles,
  setPositionRoles,
  type PermissionRef,
  type Position,
  type Role,
  type RoleScope,
} from 'src/features/hr/hr.api';

const $q = useQuasar();

const loading = ref(false);
const saving = ref(false);
const positions = ref<Position[]>([]);
const roles = ref<Role[]>([]);

const columns: QTableColumn<Position>[] = [
  { name: 'name', label: 'Puesto', field: 'name', align: 'left' },
  { name: 'code', label: 'Código', field: 'code', align: 'left' },
  { name: 'estado', label: 'Estado', field: 'is_active', align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

// Cartas de puesto/rol derivadas de los roles precargados (nombre amable + descripción).
interface RoleCard {
  id: number;
  name: string;
  friendly: string;
  blurb: string;
  permissions: PermissionRef[];
}

const roleCards = computed<RoleCard[]>(() =>
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

const pickerDialog = ref(false);
const pickerSearch = ref('');
const customName = ref('');

const filteredRoleCards = computed(() => {
  const q = pickerSearch.value.trim().toLowerCase();
  if (!q) return roleCards.value;
  return roleCards.value.filter(
    (c) =>
      c.friendly.toLowerCase().includes(q) ||
      c.name.toLowerCase().includes(q) ||
      c.blurb.toLowerCase().includes(q),
  );
});

async function reload() {
  loading.value = true;
  try {
    positions.value = await listPositions();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudieron cargar los puestos.' });
  } finally {
    loading.value = false;
  }
}

async function ensureRoles() {
  if (roles.value.length > 0) return;
  try {
    roles.value = await listRoles();
  } catch {
    /* sin roles disponibles */
  }
}

async function openPicker() {
  pickerSearch.value = '';
  customName.value = '';
  await ensureRoles();
  pickerDialog.value = true;
}

async function createFromRole(card: RoleCard) {
  saving.value = true;
  try {
    const id = await createPosition({ name: card.friendly });
    await setPositionRoles(id, [{ role_id: card.id, scope_mode: 'BRANCH' }]);
    $q.notify({ type: 'positive', message: `Puesto "${card.friendly}" creado con su rol.` });
    pickerDialog.value = false;
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e) || 'No se pudo crear el puesto.' });
  } finally {
    saving.value = false;
  }
}

async function createCustom() {
  const name = customName.value.trim();
  if (!name) return;
  saving.value = true;
  try {
    await createPosition({ name });
    customName.value = '';
    $q.notify({ type: 'positive', message: `Puesto "${name}" creado.` });
    pickerDialog.value = false;
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e) || 'No se pudo crear el puesto.' });
  } finally {
    saving.value = false;
  }
}

// --- Ajustar roles de un puesto existente ---
const rolesDialog = ref(false);
const rolesTarget = ref<Position | null>(null);
const roleRows = reactive<{ role_id: number | null; scope_mode: RoleScope }[]>([]);

const roleOptions = computed(() =>
  roles.value.map((r) => ({ label: r.name, value: r.id, description: r.description })),
);

function addRoleRow() {
  roleRows.push({ role_id: null, scope_mode: 'BRANCH' });
}

async function openRoles(p: Position) {
  rolesTarget.value = p;
  roleRows.splice(0, roleRows.length);
  await ensureRoles();
  // Precargar los roles que el puesto YA tiene (evita que el reemplazo total los borre).
  try {
    const current = await getPositionRoles(p.id);
    for (const m of current) {
      roleRows.push({ role_id: m.role_id, scope_mode: m.scope_mode });
    }
  } catch {
    /* si falla, se edita desde vacío */
  }
  if (roleRows.length === 0) addRoleRow();
  rolesDialog.value = true;
}

async function saveRoles() {
  if (!rolesTarget.value) return;
  const maps = roleRows
    .filter((r): r is { role_id: number; scope_mode: RoleScope } => r.role_id != null)
    .map((r) => ({ role_id: r.role_id, scope_mode: r.scope_mode }));
  saving.value = true;
  try {
    await setPositionRoles(rolesTarget.value.id, maps);
    $q.notify({ type: 'positive', message: 'Roles del puesto actualizados.' });
    rolesDialog.value = false;
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudieron guardar los roles.' });
  } finally {
    saving.value = false;
  }
}

onMounted(reload);
</script>

<style scoped>





/* Botón con forma y tamaño de campo (reemplaza al input "Nombre del puesto"). */
.hr-picker-trigger {
  display: flex;
  align-items: center;
  gap: var(--app-space-2);
  width: 100%;
  max-width: 480px;
  height: 44px;
  padding: 0 var(--app-space-4);
  border: 1px solid var(--app-border-strong);
  border-radius: var(--app-radius-md);
  background: var(--app-surface);
  color: var(--app-text);
  font-size: 0.95rem;
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}

.hr-picker-trigger:hover {
  border-color: var(--app-primary);
  box-shadow: var(--app-shadow-soft);
}

.hr-picker-trigger__label {
  flex: 1;
  text-align: left;
  color: var(--app-text-muted);
}

.hr-picker-trigger__chev {
  color: var(--app-text-muted);
}


.hr-picker {
  width: 760px;
  max-width: 94vw;
  background: var(--app-surface-strong);
}

.hr-picker__search {
  min-width: 220px;
}

.hr-picker__body {
  max-height: 70vh;
  overflow: auto;
}

.hr-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--app-space-3);
}

.hr-rolecard {
  display: flex;
  flex-direction: column;
  gap: var(--app-space-1);
  text-align: left;
  padding: var(--app-space-4);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  background: var(--app-surface);
  color: var(--app-text);
}

.hr-rolecard__title {
  font-weight: 800;
  font-size: 1rem;
}

.hr-rolecard__desc {
  font-size: 0.78rem;
  color: var(--app-text-muted);
  flex: 1;
}

.hr-rolecard__permcount {
  font-size: 0.74rem;
  font-weight: 700;
  color: var(--app-text);
}

.hr-rolecard__perms {
  margin: 0;
  padding: 0 2px;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 140px;
  overflow-y: auto;
}

.hr-perm-item {
  position: relative;
  padding-left: 12px;
  font-size: 0.72rem;
  line-height: 1.35;
  color: var(--app-text-muted);
}

.hr-perm-item::before {
  content: '•';
  position: absolute;
  left: 0;
  color: var(--app-secondary);
}

.hr-rolecard__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--app-space-2);
  margin-top: var(--app-space-2);
}

.hr-perm-empty {
  padding-left: 12px;
  font-size: 0.7rem;
  color: var(--app-text-muted);
  font-style: italic;
}

.hr-rolecard__tag {
  margin-top: var(--app-space-2);
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--app-primary);
}

.hr-custom {
  display: flex;
  align-items: center;
  gap: var(--app-space-3);
}

.hr-custom .q-field {
  flex: 1;
}


.hr-rolerow {
  display: flex;
  align-items: center;
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-3);
}

.hr-rolerow .col {
  flex: 1;
}

</style>
