<template>
  <q-page class="q-pa-md">
    <div class="text-h6">Dashboard</div>
    <div class="text-caption text-grey-7">Base lista: Auth + ACL + Contexto + Guards</div>

    <q-card class="q-mt-md">
      <q-card-section>
        <div><b>Company:</b> {{ companyLabel }}</div>
        <div><b>Branch:</b> {{ branchLabel }}</div>
        <div class="q-mt-sm text-caption text-grey-7">
          Si esto está seteado, ya puedes empezar ORG/HR/RBAC/Sync sin romper por headers.
        </div>

        <div class="q-mt-md">
          <q-btn label="Cambiar contexto" flat @click="goContext" />
          <q-btn label="Logout" color="negative" class="q-ml-sm" @click="doLogout" />
        </div>
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from 'src/stores/auth.store';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

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

async function goContext() {
  await router.push('/select-context');
}

async function doLogout() {
  await auth.logout();
  await router.replace('/login');
}
</script>
