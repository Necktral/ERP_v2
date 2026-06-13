<template>
  <q-page class="app-page">
    <PageHeader
      title="Finca"
      subtitle="Fincas del grupo, lotes de cultivo y catálogo de labores. Las órdenes de trabajo y el costeo están en sus pantallas."
      :loading="cargando"
      @refresh="recargar"
    >
      <template #actions>
        <q-btn
          v-if="puede('finca.work.read')"
          flat
          no-caps
          icon="agriculture"
          label="Órdenes de trabajo"
          to="/finca/ordenes"
        />
        <q-btn
          v-if="puede('finca.field.read')"
          flat
          no-caps
          icon="payments"
          label="Costos"
          to="/finca/costos"
        />
        <q-btn
          v-if="puede('finca.budget.read')"
          flat
          no-caps
          icon="request_quote"
          label="Presupuesto"
          to="/finca/presupuesto"
        />
      </template>
    </PageHeader>

    <q-tabs
      v-model="tab"
      dense
      no-caps
      align="left"
      class="fin-tabs"
      active-color="primary"
      indicator-color="primary"
    >
      <q-tab name="fincas" icon="landscape" label="Fincas" />
      <q-tab v-if="puede('finca.plot.read')" name="lotes" icon="grid_on" label="Lotes" />
      <q-tab v-if="puede('finca.labor.read')" name="labores" icon="handyman" label="Labores" />
    </q-tabs>
    <q-separator class="q-mb-md" />

    <q-tab-panels v-model="tab" animated class="fin-panels">
      <!-- ============ FINCAS ============ -->
      <q-tab-panel name="fincas" class="q-pa-none">
        <div class="text-caption text-muted q-mb-sm">
          Cada finca es una sucursal de la empresa con su perfil agrícola (zona, manzanas, GPS).
        </div>
        <q-table
          class="app-table"
          :rows="fincas"
          :columns="columnasFinca"
          row-key="finca_id"
          flat
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="No hay fincas (creá sucursales en Organización)."
        >
          <template #body-cell-acciones="props">
            <q-td :props="props" class="text-right">
              <q-btn
                v-if="puede('finca.finca.manage')"
                flat
                dense
                no-caps
                size="sm"
                icon="edit"
                label="Perfil"
                @click="abrirPerfil(props.row)"
              />
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>

      <!-- ============ LOTES ============ -->
      <q-tab-panel name="lotes" class="q-pa-none">
        <div class="app-actions">
          <q-btn
            v-if="puede('finca.plot.manage')"
            unelevated
            no-caps
            color="primary"
            icon="add"
            label="Nuevo lote"
            @click="abrirLote(null)"
          />
        </div>
        <q-table
          class="app-table"
          :rows="lotes"
          :columns="columnasLote"
          row-key="id"
          flat
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="Aún no hay lotes."
        >
          <template #body-cell-finca="props">
            <q-td :props="props">{{ nombreFinca(props.row.finca) }}</q-td>
          </template>
          <template #body-cell-acciones="props">
            <q-td :props="props" class="text-right">
              <q-btn
                v-if="puede('finca.plot.manage')"
                flat
                dense
                no-caps
                size="sm"
                icon="edit"
                label="Editar"
                @click="abrirLote(props.row)"
              />
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>

      <!-- ============ LABORES ============ -->
      <q-tab-panel name="labores" class="q-pa-none">
        <div class="app-actions">
          <q-btn
            v-if="puede('finca.labor.manage')"
            unelevated
            no-caps
            color="primary"
            icon="add"
            label="Nueva labor"
            @click="dlgLabor = true"
          />
          <span class="text-caption text-muted">
            Catálogo de labores (fertilización, poda, corte…). Las globales vienen del sistema.
          </span>
        </div>
        <q-table
          class="app-table"
          :rows="labores"
          :columns="columnasLabor"
          row-key="id"
          flat
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="Sin labores."
        >
          <template #body-cell-categoria="props">
            <q-td :props="props">{{ LABOR_CATEGORY_LABELS[props.row.category] ?? props.row.category }}</q-td>
          </template>
          <template #body-cell-unidad="props">
            <q-td :props="props">{{ LABOR_UNIT_LABELS[props.row.unit] ?? props.row.unit }}</q-td>
          </template>
          <template #body-cell-origen="props">
            <q-td :props="props">
              <q-chip v-if="props.row.is_global" dense outline color="primary" label="Global" />
              <q-chip v-else dense outline color="secondary" label="Empresa" />
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>
    </q-tab-panels>

    <!-- Diálogo: perfil de finca -->
    <q-dialog v-model="dlgPerfil">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Perfil de {{ fincaEnEdicion?.name ?? 'finca' }}</q-card-section>
        <q-card-section class="app-form">
          <q-input v-model="formPerfil.department" outlined dense label="Departamento" />
          <q-input v-model="formPerfil.municipio" outlined dense label="Municipio" />
          <q-input v-model="formPerfil.zona" outlined dense label="Zona" />
          <q-input v-model="formPerfil.area_manzanas" outlined dense type="number" min="0" label="Área (manzanas)" />
          <q-toggle v-model="formPerfil.is_headquarters" label="Es la sede principal" color="primary" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="Guardar" :loading="guardando" @click="guardarPerfil" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: lote -->
    <q-dialog v-model="dlgLote">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">{{ loteEnEdicion ? `Editar lote ${loteEnEdicion.code}` : 'Nuevo lote' }}</q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-if="!loteEnEdicion"
            v-model="formLote.finca_id"
            :options="opcionesFinca"
            label="Finca *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-input v-if="!loteEnEdicion" v-model="formLote.code" outlined dense label="Código del lote *" />
          <q-input v-model="formLote.name" outlined dense label="Nombre" />
          <q-input v-model="formLote.area_manzanas" outlined dense type="number" min="0" label="Área (manzanas)" />
          <q-input v-model="formLote.variety" outlined dense label="Variedad (ej. Caturra)" />
          <q-input v-model.number="formLote.planting_year" outlined dense type="number" label="Año de siembra" />
          <q-toggle v-if="loteEnEdicion" v-model="formLote.is_active" label="Lote activo" color="primary" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            :label="loteEnEdicion ? 'Guardar' : 'Crear lote'"
            :loading="guardando"
            :disable="!loteEnEdicion && (formLote.finca_id == null || !formLote.code.trim())"
            @click="guardarLote"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: labor -->
    <q-dialog v-model="dlgLabor">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Nueva labor</q-card-section>
        <q-card-section class="app-form">
          <q-input v-model="formLabor.code" outlined dense label="Código *" />
          <q-input v-model="formLabor.name" outlined dense label="Nombre *" />
          <q-select
            v-model="formLabor.category"
            :options="opcionesCategoria"
            label="Categoría *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-select
            v-model="formLabor.unit"
            :options="opcionesUnidad"
            label="Unidad *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-toggle v-model="formLabor.is_piecework" label="Al destajo" color="primary" />
          <q-input v-model="formLabor.default_rate" outlined dense type="number" min="0" label="Tarifa por unidad C$" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Crear labor"
            :loading="guardando"
            :disable="!formLabor.code.trim() || !formLabor.name.trim()"
            @click="guardarLabor"
          />
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
import { formatQty } from 'src/core/format';
import {
  createLabor,
  createPlot,
  LABOR_CATEGORY_LABELS,
  LABOR_UNIT_LABELS,
  listFincas,
  listLabors,
  listPlots,
  updateFincaProfile,
  updatePlot,
  type FincaRow,
  type Labor,
  type Plot,
} from 'src/features/finca/finca.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const tab = ref('fincas');
const cargando = ref(false);
const guardando = ref(false);

const fincas = ref<FincaRow[]>([]);
const lotes = ref<Plot[]>([]);
const labores = ref<Labor[]>([]);

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

function nombreFinca(fincaId: number): string {
  const f = fincas.value.find((x) => Number(x.finca_id) === fincaId);
  return (f?.name as string) ?? `Finca #${fincaId}`;
}

const opcionesFinca = computed(() =>
  fincas.value.map((f) => ({ value: Number(f.finca_id), label: (f.name as string) ?? `#${f.finca_id}` })),
);
const opcionesCategoria = Object.entries(LABOR_CATEGORY_LABELS).map(([value, label]) => ({ value, label }));
const opcionesUnidad = Object.entries(LABOR_UNIT_LABELS).map(([value, label]) => ({ value, label }));

const columnasFinca: QTableColumn<FincaRow>[] = [
  { name: 'name', label: 'Finca', field: (r) => (r.name as string) ?? `#${r.finca_id}`, align: 'left' },
  { name: 'department', label: 'Departamento', field: (r) => (r.department as string) ?? '', align: 'left' },
  { name: 'zona', label: 'Zona', field: (r) => (r.zona as string) ?? '', align: 'left' },
  { name: 'area', label: 'Manzanas', field: (r) => formatQty(r.area_manzanas), align: 'right' },
  { name: 'acciones', label: '', field: 'finca_id', align: 'right' },
];

const columnasLote: QTableColumn<Plot>[] = [
  { name: 'code', label: 'Código', field: 'code', align: 'left', sortable: true },
  { name: 'name', label: 'Nombre', field: 'name', align: 'left' },
  { name: 'finca', label: 'Finca', field: 'finca', align: 'left' },
  { name: 'area', label: 'Manzanas', field: (r) => formatQty(r.area_manzanas), align: 'right' },
  { name: 'variety', label: 'Variedad', field: 'variety', align: 'left' },
  { name: 'year', label: 'Siembra', field: 'planting_year', align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

const columnasLabor: QTableColumn<Labor>[] = [
  { name: 'code', label: 'Código', field: 'code', align: 'left' },
  { name: 'name', label: 'Labor', field: 'name', align: 'left', sortable: true },
  { name: 'categoria', label: 'Categoría', field: 'category', align: 'left' },
  { name: 'unidad', label: 'Unidad', field: 'unit', align: 'left' },
  { name: 'tarifa', label: 'Tarifa', field: (r) => (r.default_rate ? formatQty(r.default_rate) : '—'), align: 'right' },
  { name: 'origen', label: 'Origen', field: 'is_global', align: 'left' },
];

async function recargar() {
  cargando.value = true;
  try {
    const tareas: Promise<void>[] = [
      listFincas().then((r) => {
        fincas.value = r;
      }),
    ];
    if (puede('finca.plot.read')) {
      tareas.push(
        listPlots().then((r) => {
          lotes.value = r;
        }),
      );
    }
    if (puede('finca.labor.read')) {
      tareas.push(
        listLabors().then((r) => {
          labores.value = r;
        }),
      );
    }
    await Promise.all(tareas);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar la finca.') });
  } finally {
    cargando.value = false;
  }
}

// --- Perfil ---
const dlgPerfil = ref(false);
const fincaEnEdicion = ref<FincaRow | null>(null);
const formPerfil = reactive({
  department: '',
  municipio: '',
  zona: '',
  area_manzanas: '0',
  is_headquarters: false,
});

function abrirPerfil(f: FincaRow) {
  fincaEnEdicion.value = f;
  Object.assign(formPerfil, {
    department: (f.department as string) ?? '',
    municipio: (f.municipio as string) ?? '',
    zona: (f.zona as string) ?? '',
    area_manzanas: (f.area_manzanas as string) ?? '0',
    is_headquarters: Boolean(f.is_headquarters),
  });
  dlgPerfil.value = true;
}

async function guardarPerfil() {
  if (!fincaEnEdicion.value) return;
  guardando.value = true;
  try {
    await updateFincaProfile(Number(fincaEnEdicion.value.finca_id), { ...formPerfil });
    dlgPerfil.value = false;
    $q.notify({ type: 'positive', message: 'Perfil guardado.' });
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo guardar el perfil.') });
  } finally {
    guardando.value = false;
  }
}

// --- Lote ---
const dlgLote = ref(false);
const loteEnEdicion = ref<Plot | null>(null);
const formLote = reactive<{
  finca_id: number | null;
  code: string;
  name: string;
  area_manzanas: string;
  variety: string;
  planting_year: number | null;
  is_active: boolean;
}>({ finca_id: null, code: '', name: '', area_manzanas: '0', variety: '', planting_year: null, is_active: true });

function abrirLote(l: Plot | null) {
  loteEnEdicion.value = l;
  Object.assign(formLote, {
    finca_id: l?.finca ?? null,
    code: l?.code ?? '',
    name: l?.name ?? '',
    area_manzanas: l?.area_manzanas ?? '0',
    variety: l?.variety ?? '',
    planting_year: l?.planting_year ?? null,
    is_active: l?.is_active ?? true,
  });
  dlgLote.value = true;
}

async function guardarLote() {
  guardando.value = true;
  try {
    if (loteEnEdicion.value) {
      await updatePlot(loteEnEdicion.value.id, {
        name: formLote.name,
        area_manzanas: formLote.area_manzanas,
        variety: formLote.variety,
        planting_year: formLote.planting_year,
        is_active: formLote.is_active,
      });
      $q.notify({ type: 'positive', message: 'Lote actualizado.' });
    } else {
      await createPlot({
        finca_id: formLote.finca_id!,
        code: formLote.code.trim(),
        name: formLote.name,
        area_manzanas: formLote.area_manzanas,
        variety: formLote.variety,
        planting_year: formLote.planting_year,
      });
      $q.notify({ type: 'positive', message: 'Lote creado.' });
    }
    dlgLote.value = false;
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo guardar el lote.') });
  } finally {
    guardando.value = false;
  }
}

// --- Labor ---
const dlgLabor = ref(false);
const formLabor = reactive({
  code: '',
  name: '',
  category: 'MANTENIMIENTO',
  unit: 'JORNAL',
  is_piecework: false,
  default_rate: '',
});

async function guardarLabor() {
  guardando.value = true;
  try {
    await createLabor({
      code: formLabor.code.trim(),
      name: formLabor.name.trim(),
      category: formLabor.category,
      unit: formLabor.unit,
      is_piecework: formLabor.is_piecework,
      ...(formLabor.default_rate ? { default_rate: Number(formLabor.default_rate).toFixed(2) } : {}),
    });
    dlgLabor.value = false;
    Object.assign(formLabor, {
      code: '',
      name: '',
      category: 'MANTENIMIENTO',
      unit: 'JORNAL',
      is_piecework: false,
      default_rate: '',
    });
    $q.notify({ type: 'positive', message: 'Labor creada.' });
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo crear la labor.') });
  } finally {
    guardando.value = false;
  }
}

onMounted(recargar);
</script>

<style scoped>
.fin-tabs {
  color: var(--app-text-muted);
}

.fin-panels {
  background: transparent;
}
</style>
