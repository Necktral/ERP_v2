<template>
  <q-page class="ctx-page">
    <div class="ctx-card app-fade-up">
      <div class="ctx-head">
        <span class="ctx-mark" aria-hidden="true">◆</span>
        <div>
          <div class="ctx-title">Elegí tu empresa</div>
          <div class="ctx-sub">Tu usuario tiene acceso a más de una. Todo lo que hagás queda en la empresa elegida.</div>
        </div>
      </div>

      <q-banner v-if="!companies.length" class="ctx-empty" rounded>
        <div class="text-weight-medium">Sin empresas disponibles</div>
        <div class="text-caption">Tu usuario no tiene membresías activas. Contactá al administrador.</div>
      </q-banner>

      <q-list v-else class="ctx-list" separator>
        <q-expansion-item
          v-for="c in companies"
          :key="String(c.company_id)"
          group="empresas"
          :label="c.company_name"
          icon="business"
          header-class="ctx-company"
          :default-opened="companies.length === 1"
        >
          <q-item
            v-for="b in c.branches"
            :key="String(b.branch_id)"
            clickable
            class="ctx-branch"
            @click="elegir(c, b)"
          >
            <q-item-section avatar><q-icon name="store" size="20px" /></q-item-section>
            <q-item-section>{{ b.branch_name }}</q-item-section>
            <q-item-section side><q-icon name="chevron_right" /></q-item-section>
          </q-item>
          <q-item clickable class="ctx-branch ctx-branch--all" @click="elegir(c, null)">
            <q-item-section avatar><q-icon name="domain" size="20px" /></q-item-section>
            <q-item-section>Toda la empresa (sin sucursal)</q-item-section>
            <q-item-section side><q-icon name="chevron_right" /></q-item-section>
          </q-item>
        </q-expansion-item>
      </q-list>

      <q-btn flat dense no-caps icon="logout" label="Salir y entrar con otro usuario" class="ctx-logout" @click="logout" />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { useAclStore, type AclBranch, type AclCompany } from 'src/stores/acl.store';
import { useAuthStore } from 'src/stores/auth.store';
import { useContextStore } from 'src/stores/context.store';

const router = useRouter();
const acl = useAclStore();
const ctx = useContextStore();
const auth = useAuthStore();

const companies = computed(() => acl.companies);

async function elegir(c: AclCompany, b: AclBranch | null) {
  ctx.setContext(c.company_id, b?.branch_id ?? null);
  await router.replace('/');
}

async function logout() {
  auth.hardClearLocal();
  await router.replace('/login');
}
</script>

<style scoped>
.ctx-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--app-space-4);
  background: var(--app-bg-gradient);
  background-color: var(--app-bg);
}

.ctx-card {
  width: 100%;
  max-width: 460px;
  display: flex;
  flex-direction: column;
  gap: var(--app-space-5);
  padding: var(--app-space-8) var(--app-space-6);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
  box-shadow: var(--app-shadow-card);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.ctx-head {
  display: flex;
  align-items: center;
  gap: var(--app-space-3);
}

.ctx-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: var(--app-radius-md);
  font-size: 1.25rem;
  color: #fff;
  background: linear-gradient(135deg, var(--app-primary), var(--app-secondary));
  box-shadow: var(--app-shadow-soft);
  flex-shrink: 0;
}

.ctx-title {
  font-size: 1.05rem;
  font-weight: 600;
}

.ctx-sub {
  font-size: 0.8rem;
  opacity: 0.7;
}

.ctx-list {
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  overflow: hidden;
}

.ctx-branch--all {
  opacity: 0.85;
}

.ctx-logout {
  align-self: center;
  opacity: 0.7;
}

.ctx-empty {
  border: 1px solid var(--app-border);
  background: transparent;
}
</style>
