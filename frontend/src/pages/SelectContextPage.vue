<template>
  <AppContainer>
    <AppPageHeader
      title="Seleccion de contexto"
      subtitle="Selecciona empresa y sucursal para habilitar los modulos operativos."
    />

    <q-card class="q-mt-md app-card">
      <q-card-section>
        <q-select
          v-model="selectedCompanyId"
          :options="companyOptions"
          label="Empresa"
          outlined
          emit-value
          map-options
        />

        <div class="q-mt-md" />

        <q-select
          v-model="selectedBranchId"
          :disable="branchOptions.length === 0"
          :options="branchOptions"
          label="Sucursal (opcional)"
          outlined
          emit-value
          map-options
          clearable
        />

        <div class="q-mt-lg">
          <q-btn
            label="Continuar"
            color="primary"
            :disable="!selectedCompanyId"
            @click="applyContext"
          />
        </div>
      </q-card-section>
    </q-card>
  </AppContainer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import { useSessionBootstrapStore } from 'src/stores/session-bootstrap.store';

const router = useRouter();
const acl = useAclStore();
const ctx = useContextStore();
const sessionBootstrap = useSessionBootstrapStore();

const selectedCompanyId = ref<string | number | null>(ctx.activeCompanyId);
const selectedBranchId = ref<string | number | null>(ctx.activeBranchId);

const companyOptions = computed(() =>
  acl.companies.map((c) => ({ label: c.company_name, value: c.company_id })),
);

const branchOptions = computed(() => {
  const selectedCompany = selectedCompanyId.value;
  const c = acl.companies.find((x) => String(x.company_id) === String(selectedCompany));
  const branches = c?.branches ?? [];
  return branches.map((b) => ({ label: b.branch_name, value: b.branch_id }));
});

watch(selectedCompanyId, () => {
  // Si cambias company, resetea branch
  selectedBranchId.value = null;
});

async function applyContext() {
  if (!selectedCompanyId.value) return;
  ctx.setContext(selectedCompanyId.value, selectedBranchId.value ?? null);
  await sessionBootstrap.loadSession({ force: true });
  await router.replace('/dashboard');
}
</script>
