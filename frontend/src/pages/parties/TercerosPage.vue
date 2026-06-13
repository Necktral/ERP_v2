<template>
  <q-page class="app-page">
    <PageHeader
      title="Terceros"
      subtitle="Directorio de clientes, proveedores y productores de la empresa. Lo usan compras, facturación y cartera."
      :loading="loading"
      @refresh="reload"
    >
      <template #actions>
        <q-btn
          v-if="puedeCrear"
          unelevated
          no-caps
          color="primary"
          icon="person_add_alt"
          label="Nuevo tercero"
          @click="abrirCrear"
        />
      </template>
    </PageHeader>

    <div class="ter-filtros">
      <q-input
        v-model="filtroQ"
        dense
        outlined
        clearable
        placeholder="Buscar por nombre, RUC o cédula…"
        class="ter-filtros__buscar"
        :debounce="350"
        @update:model-value="reload"
      >
        <template #prepend><q-icon name="search" /></template>
      </q-input>
      <q-select
        v-model="filtroRol"
        :options="opcionesRol"
        dense
        outlined
        emit-value
        map-options
        clearable
        label="Rol"
        class="ter-filtros__sel"
        @update:model-value="reload"
      />
      <q-select
        v-model="filtroEstado"
        :options="opcionesEstado"
        dense
        outlined
        emit-value
        map-options
        clearable
        label="Estado"
        class="ter-filtros__sel"
        @update:model-value="reload"
      />
    </div>

    <q-table
      class="app-table"
      :rows="rows"
      :columns="columns"
      row-key="id"
      flat
      :loading="loading"
      :pagination="{ rowsPerPage: 25 }"
      no-data-label="No hay terceros. Creá el primero con «Nuevo tercero»."
    >
      <template #body-cell-tipo="props">
        <q-td :props="props">{{ PARTY_TYPE_LABELS[props.row.party_type as PartyType] }}</q-td>
      </template>
      <template #body-cell-roles="props">
        <q-td :props="props">
          <div class="ter-chips">
            <q-chip
              v-for="r in props.row.roles"
              :key="r"
              dense
              outline
              color="primary"
              :label="PARTY_ROLE_LABELS[r as PartyRoleCode]"
            />
            <span v-if="props.row.roles.length === 0" class="text-caption text-muted">—</span>
          </div>
        </q-td>
      </template>
      <template #body-cell-estado="props">
        <q-td :props="props">
          <q-chip
            v-if="props.row.status === 'ACTIVE'"
            dense
            color="secondary"
            text-color="white"
            label="Activo"
          />
          <q-chip
            v-else-if="props.row.status === 'BLOCKED'"
            dense
            color="negative"
            text-color="white"
            label="Bloqueado"
          />
          <q-chip v-else dense outline color="grey-7" label="Inactivo" />
        </q-td>
      </template>
      <template #body-cell-acciones="props">
        <q-td :props="props" class="text-right ter-acciones">
          <q-btn
            v-if="puedeEditar"
            flat
            dense
            no-caps
            size="sm"
            icon="edit"
            label="Editar"
            @click="abrirEditar(props.row)"
          />
          <q-btn
            v-if="puedeRoles"
            flat
            dense
            no-caps
            size="sm"
            icon="badge"
            label="Roles"
            @click="abrirRoles(props.row)"
          />
        </q-td>
      </template>
    </q-table>

    <!-- Diálogo crear/editar -->
    <q-dialog v-model="dlgForm">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">
          {{ enEdicion ? `Editar "${enEdicion.display_name}"` : 'Nuevo tercero' }}
        </q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="form.party_type"
            :options="opcionesTipo"
            label="Tipo *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-input
            v-model="form.display_name"
            outlined
            dense
            label="Nombre *"
            autofocus
            :rules="[(v) => !!String(v).trim() || 'El nombre es obligatorio']"
          />
          <q-input v-model="form.legal_name" outlined dense label="Razón social" />
          <q-input v-model="form.tax_id" outlined dense label="RUC" />
          <q-input v-model="form.national_id" outlined dense label="Cédula" />
          <q-input v-model="form.email" outlined dense label="Correo" type="email" />
          <q-input v-model="form.phone" outlined dense label="Teléfono" />
          <q-select
            v-if="!enEdicion"
            v-model="form.roles"
            :options="opcionesRol"
            label="Roles iniciales"
            outlined
            dense
            multiple
            emit-value
            map-options
            use-chips
            hint="Qué es para tu empresa: cliente, proveedor, productor…"
          />
          <q-select
            v-else
            v-model="form.status"
            :options="opcionesEstado"
            label="Estado"
            outlined
            dense
            emit-value
            map-options
            hint="Bloqueado = no se le puede vender ni comprar."
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            :label="enEdicion ? 'Guardar cambios' : 'Crear tercero'"
            :loading="guardando"
            :disable="!form.display_name.trim()"
            @click="guardar"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo roles -->
    <q-dialog v-model="dlgRoles">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Roles de "{{ enEdicion?.display_name }}"</q-card-section>
        <q-card-section>
          <div class="text-caption text-muted q-mb-md">
            Activá o quitá lo que este tercero es para la empresa. El cambio aplica al instante.
          </div>
          <div class="ter-roles-grid">
            <q-toggle
              v-for="(rotulo, code) in PARTY_ROLE_LABELS"
              :key="code"
              :model-value="rolesActivos.includes(code)"
              :label="rotulo"
              :disable="cambiandoRol === code"
              color="primary"
              @update:model-value="(v: boolean) => toggleRol(code, v)"
            />
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cerrar" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import { apiErrorMessage } from 'src/core/api';
import { useListado } from 'src/core/composables/useListado';
import PageHeader from 'src/components/PageHeader.vue';
import {
  assignPartyRole,
  createParty,
  listParties,
  PARTY_ROLE_LABELS,
  PARTY_STATUS_LABELS,
  PARTY_TYPE_LABELS,
  revokePartyRole,
  updateParty,
  type Party,
  type PartyRoleCode,
  type PartyStatus,
  type PartyType,
} from 'src/features/parties/parties.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const filtroQ = ref('');
const filtroRol = ref<PartyRoleCode | null>(null);
const filtroEstado = ref<PartyStatus | null>(null);

const { rows, loading, reload } = useListado<Party>(
  () =>
    listParties({
      q: filtroQ.value?.trim() ?? '',
      role: filtroRol.value ?? '',
      status: filtroEstado.value ?? '',
    }),
  { errorMessage: 'No se pudieron cargar los terceros.' },
);

function tienePermiso(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

const puedeCrear = computed(() => tienePermiso('parties.party.create'));
const puedeEditar = computed(() => tienePermiso('parties.party.update'));
const puedeRoles = computed(() => tienePermiso('parties.role.manage'));

const opcionesRol = Object.entries(PARTY_ROLE_LABELS).map(([value, label]) => ({ value, label }));
const opcionesTipo = Object.entries(PARTY_TYPE_LABELS).map(([value, label]) => ({ value, label }));
const opcionesEstado = Object.entries(PARTY_STATUS_LABELS).map(([value, label]) => ({
  value,
  label,
}));

const columns: QTableColumn<Party>[] = [
  { name: 'display_name', label: 'Nombre', field: 'display_name', align: 'left', sortable: true },
  { name: 'tipo', label: 'Tipo', field: 'party_type', align: 'left' },
  { name: 'tax_id', label: 'RUC', field: 'tax_id', align: 'left' },
  { name: 'national_id', label: 'Cédula', field: 'national_id', align: 'left' },
  { name: 'phone', label: 'Teléfono', field: 'phone', align: 'left' },
  { name: 'roles', label: 'Roles', field: 'id', align: 'left' },
  { name: 'estado', label: 'Estado', field: 'status', align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

// --- Crear / editar ---
const dlgForm = ref(false);
const guardando = ref(false);
const enEdicion = ref<Party | null>(null);
const form = reactive<{
  party_type: PartyType;
  display_name: string;
  legal_name: string;
  tax_id: string;
  national_id: string;
  email: string;
  phone: string;
  status: PartyStatus;
  roles: PartyRoleCode[];
}>({
  party_type: 'NATURAL',
  display_name: '',
  legal_name: '',
  tax_id: '',
  national_id: '',
  email: '',
  phone: '',
  status: 'ACTIVE',
  roles: [],
});

function abrirCrear() {
  enEdicion.value = null;
  Object.assign(form, {
    party_type: 'NATURAL',
    display_name: '',
    legal_name: '',
    tax_id: '',
    national_id: '',
    email: '',
    phone: '',
    status: 'ACTIVE',
    roles: [],
  });
  dlgForm.value = true;
}

function abrirEditar(p: Party) {
  enEdicion.value = p;
  Object.assign(form, {
    party_type: p.party_type,
    display_name: p.display_name,
    legal_name: p.legal_name,
    tax_id: p.tax_id,
    national_id: p.national_id,
    email: p.email,
    phone: p.phone,
    status: p.status,
    roles: [...p.roles],
  });
  dlgForm.value = true;
}

async function guardar() {
  const nombre = form.display_name.trim();
  if (!nombre) return;
  guardando.value = true;
  try {
    if (enEdicion.value) {
      await updateParty(enEdicion.value.id, {
        party_type: form.party_type,
        display_name: nombre,
        legal_name: form.legal_name,
        tax_id: form.tax_id,
        national_id: form.national_id,
        email: form.email,
        phone: form.phone,
        status: form.status,
      });
      $q.notify({ type: 'positive', message: 'Tercero actualizado.' });
    } else {
      await createParty({
        party_type: form.party_type,
        display_name: nombre,
        legal_name: form.legal_name,
        tax_id: form.tax_id,
        national_id: form.national_id,
        email: form.email,
        phone: form.phone,
        roles: form.roles,
      });
      $q.notify({ type: 'positive', message: `Tercero "${nombre}" creado.` });
    }
    dlgForm.value = false;
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo guardar el tercero.') });
  } finally {
    guardando.value = false;
  }
}

// --- Roles ---
const dlgRoles = ref(false);
const rolesActivos = ref<PartyRoleCode[]>([]);
const cambiandoRol = ref<PartyRoleCode | null>(null);

function abrirRoles(p: Party) {
  enEdicion.value = p;
  rolesActivos.value = [...p.roles];
  dlgRoles.value = true;
}

async function toggleRol(code: PartyRoleCode, activar: boolean) {
  if (!enEdicion.value) return;
  cambiandoRol.value = code;
  try {
    const actualizado = activar
      ? await assignPartyRole(enEdicion.value.id, code)
      : await revokePartyRole(enEdicion.value.id, code);
    rolesActivos.value = [...actualizado.roles];
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cambiar el rol.') });
  } finally {
    cambiandoRol.value = null;
  }
}
</script>

<style scoped>
.ter-filtros {
  display: flex;
  flex-wrap: wrap;
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-4);
}

.ter-filtros__buscar {
  width: 320px;
  max-width: 100%;
}

.ter-filtros__sel {
  width: 180px;
}

.ter-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.ter-acciones {
  white-space: nowrap;
}

.ter-roles-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(180px, 1fr));
  gap: var(--app-space-1) var(--app-space-4);
}
</style>
