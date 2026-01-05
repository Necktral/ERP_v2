<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated>
      <q-toolbar>
        <q-btn flat dense round icon="menu" @click="drawer = !drawer" />
        <q-toolbar-title>Necktral Console</q-toolbar-title>

        <div class="text-caption text-grey-3">
          {{ ctxLabel }}
        </div>

        <q-btn flat label="Logout" class="q-ml-md" @click="doLogout" />
      </q-toolbar>
    </q-header>

    <q-drawer v-model="drawer" show-if-above bordered>
      <q-list>
        <q-item clickable v-ripple to="/dashboard">
          <q-item-section>Dashboard</q-item-section>
        </q-item>

        <q-separator />

        <q-item v-if="canCompanyProfile" clickable v-ripple to="/org/company-profile">
          <q-item-section>Company Profile</q-item-section>
        </q-item>

        <q-item v-if="canBranches" clickable v-ripple to="/org/branches">
          <q-item-section>Branches</q-item-section>
        </q-item>

        <q-separator />

        <q-item v-if="canHrPositions" clickable v-ripple to="/hr/positions">
          <q-item-section>HR · Puestos</q-item-section>
        </q-item>

        <q-item v-if="canHrEmployees" clickable v-ripple to="/hr/employees">
          <q-item-section>HR · Empleados</q-item-section>
        </q-item>

        <q-separator />

        <q-item clickable v-ripple to="/select-context">
          <q-item-section>Cambiar contexto</q-item-section>
        </q-item>
      </q-list>
    </q-drawer>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from 'src/stores/auth.store';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const drawer = ref(true);

const router = useRouter();
const auth = useAuthStore();
const acl = useAclStore();
const ctx = useContextStore();

const ctxLabel = computed(() => {
  const c = acl.companyName(ctx.activeCompanyId) ?? ctx.activeCompanyId ?? '—';
  const b = acl.branchName(ctx.activeCompanyId, ctx.activeBranchId) ?? ctx.activeBranchId ?? '—';
  return `Company: ${c} | Branch: ${b}`;
});

const canHrPositions = computed(() => {
  if (!ctx.activeCompanyId) return false;
  return acl.hasPermission(ctx.activeCompanyId, 'hr.position.read');
});

const canHrEmployees = computed(() => {
  if (!ctx.activeCompanyId) return false;
  return acl.hasPermission(ctx.activeCompanyId, 'hr.employee.read');
});

const canCompanyProfile = computed(() => {
  if (!ctx.activeCompanyId) return false;
  return acl.hasPermission(ctx.activeCompanyId, 'org.company.update');
});

const canBranches = computed(() => {
  if (!ctx.activeCompanyId) return false;
  return acl.hasPermission(ctx.activeCompanyId, 'org.branch.read');
});

async function doLogout() {
  await auth.logout();
  await router.replace('/login');
}
</script>
