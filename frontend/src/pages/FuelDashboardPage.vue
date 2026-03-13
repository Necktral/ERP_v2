<template>
  <AppContainer>
    <AppPageHeader
      :title="`${labels.fuel} · Tablero operativo`"
      subtitle="Modulo de estacion de servicios y monitoreo operativo"
    >
        <template #actions>
          <q-btn
            outline
            icon="monitor_heart"
            label="Estado operativo"
            :disable="!canFuelRead"
            :to="routes.fuelHealth"
          />
        </template>
    </AppPageHeader>

    <q-banner v-if="!canFuelRead" dense rounded class="q-mb-md q-mt-md">
      No tienes permiso <b>fuel.shift.read</b> o no hay contexto de empresa.
    </q-banner>

    <div v-else class="row q-col-gutter-md q-mt-md">
      <div class="col-12 col-md-6 col-lg-4">
        <q-card class="app-card">
          <q-card-section>
            <div class="text-subtitle1">Estado operativo</div>
            <div class="text-caption text-grey-7">Verifica conectividad y autenticacion del modulo.</div>
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Abrir" :to="routes.fuelHealth" />
          </q-card-actions>
        </q-card>
      </div>

      <div class="col-12 col-md-6 col-lg-4">
        <q-card class="app-card">
          <q-card-section>
            <div class="text-subtitle1">Operacion en progreso</div>
            <div class="text-caption text-grey-7">
              Turnos, despachos, ventas, tanques, conciliacion e intercompany.
            </div>
          </q-card-section>
          <q-card-section class="text-caption">
            <ul class="q-pl-md q-my-none">
              <li>Turnos de apertura y cierre</li>
              <li>Despachos y anulaciones</li>
              <li>Ventas y anulaciones</li>
              <li>Recepciones y ajustes de tanque</li>
              <li>Conciliacion operativa</li>
            </ul>
          </q-card-section>
        </q-card>
      </div>

      <div class="col-12 col-md-6 col-lg-4">
        <q-card class="app-card">
          <q-card-section>
            <div class="text-subtitle1">Nucleo modular</div>
            <div class="text-caption text-grey-7">
              Base compartida para operaciones multi negocio.
            </div>
          </q-card-section>
          <q-card-section class="text-caption">
            <ul class="q-pl-md q-my-none">
              <li>Facturacion multi negocio</li>
              <li>Inventarios por sucursal</li>
              <li>{{ labels.rolesAndPermissions }} y {{ labels.accessControl }}</li>
              <li>Auditoria contractual por evento de modulo</li>
            </ul>
          </q-card-section>
        </q-card>
      </div>
    </div>
  </AppContainer>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import { BUSINESS_LABELS, UI_ROUTE_PATHS } from 'src/shared/ui/business-terms';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const acl = useAclStore();
const ctx = useContextStore();
const labels = BUSINESS_LABELS;
const routes = UI_ROUTE_PATHS;

const canFuelRead = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'fuel.shift.read');
});
</script>
