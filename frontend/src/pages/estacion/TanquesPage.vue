<template>
  <q-page class="app-page">
    <PageHeader
      title="Tanques de combustible"
      subtitle="Nivel de cada tanque (sube con recepciones, baja con despachos), recepciones y ajustes."
      :loading="cargando"
      @refresh="recargar"
    >
      <template #actions>
        <q-btn
          v-if="puede('fuel.config.update')"
          unelevated no-caps color="primary" icon="add" label="Nuevo tanque"
          @click="abrirNuevo"
        />
      </template>
    </PageHeader>

    <div class="tk-grid">
      <q-card v-for="t in tanques" :key="t.id" flat class="tk-card" :class="{ 'tk-card--low': t.is_low }">
        <q-card-section class="tk-card__head">
          <div>
            <div class="tk-card__code">{{ t.code }}</div>
            <div class="tk-muted">{{ t.product_label }}</div>
          </div>
          <q-chip v-if="t.is_low" dense color="negative" text-color="white" label="Nivel bajo" />
        </q-card-section>
        <q-card-section>
          <div class="tk-level">{{ Number(t.current_volume_l).toLocaleString('es-NI') }} L</div>
          <q-linear-progress
            :value="(t.pct ?? 0) / 100"
            size="14px"
            rounded
            :color="t.is_low ? 'negative' : 'secondary'"
            track-color="grey-3"
            class="q-mt-xs"
          />
          <div class="tk-muted q-mt-xs">
            {{ t.pct != null ? t.pct + '%' : '—' }} de {{ Number(t.capacity_l).toLocaleString('es-NI') }} L
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat dense no-caps size="sm" icon="history" label="Movimientos" @click="abrirDetalle(t)" />
          <q-btn
            v-if="puede('fuel.tank.receive')"
            flat dense no-caps size="sm" color="secondary" icon="local_shipping" label="Recibir" @click="abrirRecepcion(t)"
          />
          <q-btn
            v-if="puede('fuel.tank.adjust')"
            flat dense no-caps size="sm" icon="tune" label="Ajustar" @click="abrirAjuste(t)"
          />
        </q-card-actions>
      </q-card>
      <div v-if="!cargando && !tanques.length" class="tk-muted">Sin tanques. Creá el primero.</div>
    </div>

    <!-- Nuevo tanque -->
    <q-dialog v-model="dlgNuevo">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Nuevo tanque</q-card-section>
        <q-card-section class="app-form">
          <q-input v-model="formTank.code" outlined dense label="Código *" />
          <q-select v-model="formTank.product" :options="productoOpts" outlined dense emit-value map-options label="Producto *" />
          <q-input v-model="formTank.capacity_l" outlined dense type="number" label="Capacidad (L) *" />
          <q-input v-model="formTank.low_level_l" outlined dense type="number" label="Alerta de nivel bajo (L)" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated no-caps color="primary" label="Crear" :loading="accionando"
            :disable="!formTank.code.trim() || !formTank.product || !formTank.capacity_l" @click="crear"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Recepción -->
    <q-dialog v-model="dlgRecepcion">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Recibir combustible — {{ activo?.code }}</q-card-section>
        <q-card-section class="app-form">
          <q-input v-model="formRec.liters" outlined dense type="number" label="Litros recibidos *" />
          <q-input v-model="formRec.unit_cost" outlined dense type="number" label="Costo por litro (opcional)" />
          <q-input v-model="formRec.supplier_name" outlined dense label="Proveedor / pipa" />
          <q-input v-model="formRec.document_ref" outlined dense label="No. de documento" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="Recibir" :loading="accionando" :disable="!formRec.liters" @click="recibir" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Ajuste -->
    <q-dialog v-model="dlgAjuste">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Ajustar nivel — {{ activo?.code }}</q-card-section>
        <q-card-section class="app-form">
          <q-input v-model="formAj.liters" outlined dense type="number" label="Litros (+ suma / − resta) *" />
          <q-input v-model="formAj.reason" outlined dense label="Motivo *" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="Aplicar" :loading="accionando" :disable="!formAj.liters || !formAj.reason.trim()" @click="ajustar" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Movimientos -->
    <q-dialog v-model="dlgDetalle">
      <q-card class="tk-dialog">
        <q-card-section class="text-h6">Movimientos — {{ detalle?.code }}</q-card-section>
        <q-card-section>
          <q-list dense bordered>
            <q-item v-for="m in detalle?.movements ?? []" :key="m.id">
              <q-item-section>
                <q-item-label>{{ m.kind_label }} · {{ new Date(m.occurred_at).toLocaleDateString('es-NI') }}</q-item-label>
                <q-item-label caption>{{ m.supplier_name || m.note }}</q-item-label>
              </q-item-section>
              <q-item-section side>
                <span :class="Number(m.liters) < 0 ? 'tk-neg' : 'tk-pos'">{{ m.liters }} L</span>
              </q-item-section>
            </q-item>
            <q-item v-if="!(detalle?.movements ?? []).length">
              <q-item-section class="tk-muted">Sin movimientos.</q-item-section>
            </q-item>
          </q-list>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cerrar" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { useQuasar } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import {
  adjustFuelTank,
  createFuelTank,
  getFuelTank,
  listFuelTanks,
  receiveFuelTank,
  type FuelTank,
  type FuelTankMovement,
} from 'src/features/fuel/fuel.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const cargando = ref(false);
const accionando = ref(false);
const tanques = ref<FuelTank[]>([]);
const productoOpts = [
  { value: 'DIESEL', label: 'Diésel' },
  { value: 'GASOLINE', label: 'Gasolina' },
];

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

async function recargar() {
  cargando.value = true;
  try {
    tanques.value = await listFuelTanks();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudieron cargar los tanques.') });
  } finally {
    cargando.value = false;
  }
}

const activo = ref<FuelTank | null>(null);

const dlgNuevo = ref(false);
const formTank = reactive({ code: '', product: 'DIESEL', capacity_l: '', low_level_l: '' });
function abrirNuevo() {
  Object.assign(formTank, { code: '', product: 'DIESEL', capacity_l: '', low_level_l: '' });
  dlgNuevo.value = true;
}
async function crear() {
  accionando.value = true;
  try {
    await createFuelTank({
      code: formTank.code.trim(),
      product: formTank.product,
      capacity_l: formTank.capacity_l,
      low_level_l: formTank.low_level_l || '0',
    });
    $q.notify({ type: 'positive', message: 'Tanque creado.' });
    dlgNuevo.value = false;
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo crear el tanque.') });
  } finally {
    accionando.value = false;
  }
}

const dlgRecepcion = ref(false);
const formRec = reactive({ liters: '', unit_cost: '', supplier_name: '', document_ref: '' });
function abrirRecepcion(t: FuelTank) {
  activo.value = t;
  Object.assign(formRec, { liters: '', unit_cost: '', supplier_name: '', document_ref: '' });
  dlgRecepcion.value = true;
}
async function recibir() {
  if (!activo.value) return;
  accionando.value = true;
  try {
    await receiveFuelTank(activo.value.id, {
      liters: formRec.liters,
      unit_cost: formRec.unit_cost || null,
      supplier_name: formRec.supplier_name,
      document_ref: formRec.document_ref,
    });
    $q.notify({ type: 'positive', message: 'Recepción registrada.' });
    dlgRecepcion.value = false;
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo registrar la recepción.') });
  } finally {
    accionando.value = false;
  }
}

const dlgAjuste = ref(false);
const formAj = reactive({ liters: '', reason: '' });
function abrirAjuste(t: FuelTank) {
  activo.value = t;
  Object.assign(formAj, { liters: '', reason: '' });
  dlgAjuste.value = true;
}
async function ajustar() {
  if (!activo.value) return;
  accionando.value = true;
  try {
    await adjustFuelTank(activo.value.id, { liters: formAj.liters, reason: formAj.reason.trim() });
    $q.notify({ type: 'positive', message: 'Ajuste aplicado.' });
    dlgAjuste.value = false;
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo ajustar.') });
  } finally {
    accionando.value = false;
  }
}

const dlgDetalle = ref(false);
const detalle = ref<(FuelTank & { movements: FuelTankMovement[] }) | null>(null);
async function abrirDetalle(t: FuelTank) {
  dlgDetalle.value = true;
  detalle.value = null;
  try {
    detalle.value = await getFuelTank(t.id);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudieron cargar los movimientos.') });
  }
}

onMounted(recargar);
</script>

<style scoped>
.tk-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--app-space-4);
}
.tk-card {
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  background: var(--app-surface);
}
.tk-card--low {
  border-color: var(--q-negative);
}
.tk-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}
.tk-card__code {
  font-weight: 800;
  font-size: 1.1rem;
  color: var(--app-text);
}
.tk-level {
  font-size: 1.6rem;
  font-weight: 800;
  color: var(--app-text);
}
.tk-muted {
  color: var(--app-text-muted);
  font-size: 0.82rem;
}
.tk-neg {
  color: var(--q-negative);
  font-weight: 700;
}
.tk-pos {
  color: var(--q-positive);
  font-weight: 700;
}
.tk-dialog {
  width: 560px;
  max-width: 95vw;
  background: var(--app-surface-strong);
}
</style>
