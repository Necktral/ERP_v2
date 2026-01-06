<template>
  <q-page>
    <AppContainer>
      <AppPageHeader
        title="Dashboard"
        subtitle="Consola base: Auth + ACL + Contexto + Guards. Siguiente paso: módulos con tablas."
      >
        <template #badges>
          <q-badge outline class="q-mr-sm">Company: {{ companyLabel }}</q-badge>
          <q-badge outline>Branch: {{ branchLabel }}</q-badge>
        </template>

        <template #actions>
          <q-btn label="Cambiar contexto" flat @click="goContext" />
          <q-btn label="Logout" color="negative" @click="doLogout" />
        </template>
      </AppPageHeader>

      <div class="q-mt-md">
        <AppDataTable
          :rows="companyRows"
          :columns="companyColumns"
          row-key="company_id"
          :loading="loadingCompanies"
          search-placeholder="Buscar company…"
          empty-label="No hay companies disponibles en tu ACL."
        >
          <template #top-left>
            <div class="text-subtitle2">Companies accesibles</div>
            <div class="text-caption text-grey-7">
              Esto refleja lo que el backend entregó en /auth/me/acl/.
            </div>
          </template>

          <template #row-actions="{ row }">
            <q-btn dense flat label="Usar" @click="useCompany(row.company_id as string)" />
            <q-btn dense flat label="Contexto" @click="goContext" />
          </template>

          <template #empty-action>
            <q-btn label="Ir a Login" color="primary" @click="goLogin" />
          </template>
        </AppDataTable>
      </div>
    </AppContainer>
  </q-page>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from 'src/stores/auth.store';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import AppDataTable from 'src/ui/AppDataTable.vue';
import type { QTableColumn } from 'quasar';

const router = useRouter();
const auth = useAuthStore();
const acl = useAclStore();
const ctx = useContextStore();

const companyLabel = computed(
  () => acl.companyName(ctx.activeCompanyId) ?? ctx.activeCompanyId ?? '—',
);
const branchLabel = computed(
  () => acl.branchName(ctx.activeCompanyId, ctx.activeBranchId) ?? ctx.activeBranchId ?? '—',
);

const loadingCompanies = computed(() => !acl.loaded);

const companyRows = computed(() =>
  (acl.companies ?? []).map((c) => ({
    company_id: c.company_id,
    company_name: c.company_name,
    branches_count: (c.branches ?? []).length,
    permissions_count: (c.permissions ?? []).length,
  })),
);

const companyColumns: QTableColumn[] = [
  { name: 'company_name', label: 'Company', field: 'company_name', align: 'left', sortable: true },
  { name: 'company_id', label: 'ID', field: 'company_id', align: 'left', sortable: true },
  {
    name: 'branches_count',
    label: 'Sucursales',
    field: 'branches_count',
    align: 'right',
    sortable: true,
  },
  {
    name: 'permissions_count',
    label: 'Permisos',
    field: 'permissions_count',
    align: 'right',
    sortable: true,
  },
];

async function goContext() {
  await router.push('/select-context');
}

async function goLogin() {
  await router.replace('/login');
}

function useCompany(companyId: string) {
  // setea company sin branch (branch opcional)
  ctx.setContext(companyId, null);
}

async function doLogout() {
  await auth.logout();
  await router.replace('/login');
}
</script>
