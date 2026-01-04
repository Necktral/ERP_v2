<template>
  <q-page class="q-pa-md">
    <div class="text-h6">Seleccionar contexto</div>
    <div class="text-caption text-grey-7">
      El backend requiere Company para operar. Selecciona Company (y Branch si aplica).
    </div>

    <div class="q-mt-md">
      <q-card>
        <q-card-section>
          <q-select
            v-model="selectedCompanyId"
            :options="companyOptions"
            label="Company"
            outlined
            emit-value
            map-options
          />

          <div class="q-mt-md" />

          <q-select
            v-model="selectedBranchId"
            :disable="branchOptions.length === 0"
            :options="branchOptions"
            label="Branch (opcional)"
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
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const router = useRouter();
const acl = useAclStore();
const ctx = useContextStore();

const selectedCompanyId = ref<string | null>(ctx.activeCompanyId);
const selectedBranchId = ref<string | null>(ctx.activeBranchId);

const companyOptions = computed(() =>
  acl.companies.map((c) => ({ label: c.company_name, value: c.company_id })),
);

const branchOptions = computed(() => {
  const c = acl.companies.find((x) => x.company_id === selectedCompanyId.value);
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
  await router.replace('/dashboard');
}
</script>
