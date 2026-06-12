<template>
  <q-page class="app-page">
    <PageHeader
      title="Contabilidad"
      subtitle="Panel del contador: diario con SoD, plan de cuentas, períodos, reportes, tipo de cambio e intercompañía."
      hide-refresh
    />

    <div class="cont-grid">
      <router-link v-for="card in tarjetasVisibles" :key="card.to" :to="card.to" class="cont-card">
        <q-icon :name="card.icon" size="32px" class="cont-card__icon" />
        <div class="cont-card__title">{{ card.title }}</div>
        <div class="cont-card__desc">{{ card.desc }}</div>
      </router-link>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import PageHeader from 'src/components/PageHeader.vue';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const acl = useAclStore();
const ctx = useContextStore();

interface Tarjeta {
  to: string;
  icon: string;
  title: string;
  desc: string;
  perm: string;
}

const TARJETAS: Tarjeta[] = [
  {
    to: '/contabilidad/diario',
    icon: 'menu_book',
    title: 'Diario',
    desc: 'Borradores por aprobar/postear (SoD) y asientos con reversa.',
    perm: 'accounting.journal_draft.read',
  },
  {
    to: '/contabilidad/plan-cuentas',
    icon: 'account_tree',
    title: 'Plan de cuentas',
    desc: 'Catálogo contable y configuración de moneda funcional.',
    perm: 'accounting.coa.read',
  },
  {
    to: '/contabilidad/periodos',
    icon: 'event',
    title: 'Períodos',
    desc: 'Cerrar y reabrir meses fiscales.',
    perm: 'accounting.period.read',
  },
  {
    to: '/contabilidad/reportes',
    icon: 'analytics',
    title: 'Reportes',
    desc: 'Balanza, mayor, resultados y balance general.',
    perm: 'accounting.report.read',
  },
  {
    to: '/contabilidad/monedas',
    icon: 'currency_exchange',
    title: 'Tipo de cambio',
    desc: 'Tasas por fecha y revaluación de moneda extranjera.',
    perm: 'accounting.fx_rate.read',
  },
  {
    to: '/contabilidad/intercompania',
    icon: 'lan',
    title: 'Intercompañía',
    desc: 'Cruces entre tus empresas y su conciliación.',
    perm: 'accounting.intercompany.read',
  },
];

const tarjetasVisibles = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return [];
  return TARJETAS.filter((t) => acl.hasPermission(companyId, t.perm));
});
</script>

<style scoped>
.cont-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--app-space-4);
}

.cont-card {
  display: flex;
  flex-direction: column;
  gap: var(--app-space-2);
  padding: var(--app-space-5);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
  text-decoration: none;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}

.cont-card:hover {
  border-color: var(--app-primary);
  box-shadow: var(--app-shadow-soft);
}

.cont-card__icon {
  color: var(--app-primary);
}

.cont-card__title {
  font-weight: 800;
  color: var(--app-text);
}

.cont-card__desc {
  font-size: 0.82rem;
  color: var(--app-text-muted);
}
</style>
