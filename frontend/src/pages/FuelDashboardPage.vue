<template>
  <q-page>
    <AppContainer>
      <AppPageHeader title="FUEL · Dashboard" subtitle="Módulo Estación de Servicios (base)">
        <template #actions>
          <q-btn
            outline
            icon="monitor_heart"
            label="Health"
            :disable="!canFuelRead"
            to="/fuel/health"
          />
        </template>
      </AppPageHeader>

      <q-banner v-if="!canFuelRead" dense rounded class="q-mb-md">
        No tienes permiso <b>fuel.shift.read</b> o no hay contexto de company.
      </q-banner>

      <div v-else class="row q-col-gutter-md">
        <div class="col-12 col-md-6 col-lg-4">
          <q-card class="app-card">
            <q-card-section>
              <div class="text-subtitle1">Health</div>
              <div class="text-caption text-grey-7">Verifica conectividad y auth del módulo.</div>
            </q-card-section>
            <q-card-actions align="right">
              <q-btn flat label="Abrir" to="/fuel/health" />
            </q-card-actions>
          </q-card>
        </div>

        <div class="col-12 col-md-6 col-lg-4">
          <q-card class="app-card">
            <q-card-section>
              <div class="text-subtitle1">Operación (próximo)</div>
              <div class="text-caption text-grey-7">
                Turnos, despachos, ventas, tanques, conciliación e intercompany.
              </div>
            </q-card-section>
            <q-card-section class="text-caption">
              <ul class="q-pl-md q-my-none">
                <li>Turnos (open/close)</li>
                <li>Despachos + anulaciones</li>
                <li>Ventas + anulaciones</li>
                <li>Recepciones/ajustes de tanque</li>
                <li>Conciliación</li>
              </ul>
            </q-card-section>
          </q-card>
        </div>

        <div class="col-12 col-md-6 col-lg-4">
          <q-card class="app-card">
            <q-card-section>
              <div class="text-subtitle1">Kernel modular (diseño)</div>
              <div class="text-caption text-grey-7">
                Base compartida para módulos multi-negocio.
              </div>
            </q-card-section>
            <q-card-section class="text-caption">
              <ul class="q-pl-md q-my-none">
                <li>Facturación multi-negocio (próximo)</li>
                <li>Inventarios (próximo)</li>
                <li>RBAC/ACL + contexto por company/branch</li>
                <li>Auditoría contractual (eventos por módulo)</li>
              </ul>
            </q-card-section>
          </q-card>
        </div>
      </div>
    </AppContainer>
  </q-page>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const acl = useAclStore();
const ctx = useContextStore();

const canFuelRead = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'fuel.shift.read');
});
</script>
