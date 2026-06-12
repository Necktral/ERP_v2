<template>
  <q-page class="app-page">
    <PageHeader
      title="Recursos Humanos"
      subtitle="Configura tu equipo: puestos, trabajadores y acceso."
      :loading="loading"
      @refresh="load"
    />

    <section class="hr-stats">
      <router-link
        v-for="c in statCards"
        :key="c.key"
        :to="c.to"
        class="hr-stat"
        :class="`hr-stat--${c.color}`"
      >
        <q-icon :name="c.icon" class="hr-stat__watermark" />
        <div class="hr-stat__body">
          <div class="hr-stat__value">{{ c.value }}</div>
          <div class="hr-stat__label">{{ c.label }}</div>
          <div v-if="c.sublabel" class="hr-stat__sublabel">{{ c.sublabel }}</div>
        </div>
        <div class="hr-stat__foot">
          <span>VER MÁS</span>
          <q-icon name="arrow_forward" size="18px" />
        </div>
      </router-link>
    </section>

    <div class="hr-steps">
      <article
        v-for="s in steps"
        :key="s.key"
        class="hr-step-card"
        :class="`is-${s.status}`"
      >
        <div class="hr-step-card__top">
          <span class="hr-step-card__num">
            <q-icon v-if="s.status === 'done'" name="check" />
            <template v-else>{{ s.index }}</template>
          </span>
          <q-badge v-if="s.status === 'active'" color="primary" label="Siguiente" />
          <q-badge v-else-if="s.status === 'done'" color="secondary" label="Listo" />
        </div>
        <div class="hr-step-card__title">{{ s.title }}</div>
        <div class="hr-step-card__desc">{{ s.desc }}</div>
        <div class="hr-step-card__meta">{{ s.meta }}</div>
        <q-btn
          :label="s.cta"
          :color="s.status === 'active' ? 'primary' : 'grey-7'"
          :flat="s.status !== 'active'"
          unelevated
          no-caps
          class="hr-step-card__btn"
          :to="s.to"
          :disable="s.disabled"
        />
      </article>
    </div>

    <q-banner v-if="summary?.complete" class="hr-done-banner" rounded>
      <template #avatar><q-icon name="celebration" color="secondary" /></template>
      ¡Onboarding completo! Tu equipo está configurado.
    </q-banner>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useQuasar } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { getOnboardingSummary, type OnboardingSummary } from 'src/features/hr/hr.api';

const $q = useQuasar();
const loading = ref(false);
const summary = ref<OnboardingSummary | null>(null);

type StatColor = 'blue' | 'coral' | 'teal' | 'amber' | 'violet';

interface StatCard {
  key: string;
  label: string;
  value: number;
  icon: string;
  color: StatColor;
  to: string;
  sublabel?: string;
}

const statCards = computed<StatCard[]>(() => {
  const s = summary.value;
  const lifecycleParts: string[] = [];
  if (s) {
    lifecycleParts.push(`${s.employees_active} activos`);
    if (s.employees_suspended > 0) lifecycleParts.push(`${s.employees_suspended} susp.`);
    if (s.employees_terminated > 0) lifecycleParts.push(`${s.employees_terminated} bajas`);
  }
  return [
    {
      key: 'employees',
      label: 'Trabajadores',
      value: s?.employees_count ?? 0,
      icon: 'groups',
      color: 'blue',
      to: '/recursos-humanos/trabajadores',
    },
    {
      key: 'profiles',
      label: 'Perfil Empleados',
      value: s?.employees_count ?? 0,
      icon: 'folder_shared',
      color: 'violet',
      to: '/recursos-humanos/trabajadores',
      sublabel: lifecycleParts.join(' · '),
    },
    {
      key: 'positions',
      label: 'Puestos',
      value: s?.positions_count ?? 0,
      icon: 'badge',
      color: 'coral',
      to: '/recursos-humanos/puestos',
    },
    {
      key: 'assigned',
      label: 'Asignados',
      value: s?.employees_assigned ?? 0,
      icon: 'assignment_ind',
      color: 'amber',
      to: '/recursos-humanos/trabajadores',
    },
    {
      key: 'provisioned',
      label: 'Con acceso',
      value: s?.employees_provisioned ?? 0,
      icon: 'verified_user',
      color: 'teal',
      to: '/recursos-humanos/trabajadores',
    },
  ];
});

type StepStatus = 'done' | 'active' | 'pending';

interface StepCard {
  key: string;
  index: number;
  title: string;
  desc: string;
  meta: string;
  cta: string;
  to: string;
  status: StepStatus;
  disabled: boolean;
}

const steps = computed<StepCard[]>(() => {
  const s = summary.value;
  const next = s?.next_step;
  const status = (done: boolean, isNext: boolean): StepStatus =>
    done ? 'done' : isNext ? 'active' : 'pending';

  return [
    {
      key: 'positions',
      index: 1,
      title: 'Puestos',
      desc: 'Define los cargos y mapea sus roles. El puesto define el permiso, no la persona.',
      meta: `${s?.positions_count ?? 0} puestos · ${s?.positions_with_roles ?? 0} con roles`,
      cta: 'Abrir puestos',
      to: '/recursos-humanos/puestos',
      status: status(
        (s?.positions_count ?? 0) > 0 && (s?.positions_with_roles ?? 0) > 0,
        next === 'POSITIONS' || next === 'POSITION_ROLES',
      ),
      disabled: false,
    },
    {
      key: 'employees',
      index: 2,
      title: 'Trabajadores',
      desc: 'Registra a las personas que trabajan en la empresa (alta rápida con TAB).',
      meta: `${s?.employees_count ?? 0} trabajadores`,
      cta: 'Abrir trabajadores',
      to: '/recursos-humanos/trabajadores',
      status: status((s?.employees_count ?? 0) > 0, next === 'EMPLOYEES'),
      disabled: false,
    },
    {
      key: 'assignments',
      index: 3,
      title: 'Asignar',
      desc: 'Asigna a cada trabajador un puesto y una sucursal. De ahí hereda sus roles.',
      meta: `${s?.employees_assigned ?? 0} asignados`,
      cta: 'Asignar',
      to: '/recursos-humanos/trabajadores',
      status: status((s?.employees_assigned ?? 0) > 0, next === 'ASSIGNMENTS'),
      disabled: false,
    },
    {
      key: 'provisioning',
      index: 4,
      title: 'Provisionar acceso',
      desc: 'Solo a quien necesita entrar al sistema: crea su usuario con clave temporal.',
      meta: `${s?.employees_provisioned ?? 0} con acceso`,
      cta: 'Provisionar',
      to: '/recursos-humanos/trabajadores',
      status: status((s?.employees_provisioned ?? 0) > 0, next === 'PROVISIONING'),
      disabled: false,
    },
  ];
});

async function load() {
  loading.value = true;
  try {
    summary.value = await getOnboardingSummary();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo cargar el estado de RR.HH.' });
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>




.hr-stats {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--app-space-4);
  margin-bottom: var(--app-space-6);
}

.hr-stat {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 132px;
  border-radius: var(--app-radius-md);
  overflow: hidden;
  color: #fff;
  text-decoration: none;
  box-shadow: var(--app-shadow-card);
  transition:
    transform 140ms ease,
    box-shadow 140ms ease;
}

.hr-stat:hover {
  transform: translateY(-2px);
  box-shadow: 0 16px 34px rgba(24, 46, 84, 0.18);
}

.hr-stat:focus-visible {
  outline: 2px solid var(--app-focus);
  outline-offset: 2px;
}

.hr-stat--blue {
  background: var(--app-stat-blue);
}
.hr-stat--coral {
  background: var(--app-stat-coral);
}
.hr-stat--teal {
  background: var(--app-stat-teal);
}
.hr-stat--amber {
  background: var(--app-stat-amber);
}
.hr-stat--violet {
  background: var(--app-stat-violet);
}

.hr-stat__watermark {
  position: absolute;
  left: -8px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 116px;
  opacity: 0.16;
  pointer-events: none;
}

.hr-stat__body {
  position: relative;
  padding: var(--app-space-4) var(--app-space-5) 0;
  text-align: right;
}

.hr-stat__value {
  font-family: 'Manrope', 'IBM Plex Sans', sans-serif;
  font-size: 2.4rem;
  font-weight: 800;
  line-height: 1;
}

.hr-stat__label {
  font-size: 0.95rem;
  font-weight: 500;
  opacity: 0.95;
  margin-top: var(--app-space-1);
}

.hr-stat__sublabel {
  font-size: 0.72rem;
  font-weight: 600;
  opacity: 0.85;
  margin-top: 2px;
}

.hr-stat__foot {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--app-space-2);
  padding: var(--app-space-2) var(--app-space-5);
  margin-top: var(--app-space-3);
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  background: rgba(0, 0, 0, 0.13);
}

.hr-steps {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--app-space-4);
}

.hr-step-card {
  display: flex;
  flex-direction: column;
  gap: var(--app-space-2);
  padding: var(--app-space-5);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
  box-shadow: var(--app-shadow-soft);
}

.hr-step-card.is-active {
  border-color: var(--app-primary);
  box-shadow: var(--app-shadow-card);
}

.hr-step-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.hr-step-card__num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  font-weight: 700;
  color: #fff;
  background: var(--app-text-muted);
}

.hr-step-card.is-active .hr-step-card__num {
  background: var(--app-primary);
}

.hr-step-card.is-done .hr-step-card__num {
  background: var(--app-secondary);
}

.hr-step-card__title {
  font-weight: 800;
  font-size: 1.05rem;
  color: var(--app-text);
}

.hr-step-card__desc {
  font-size: 0.82rem;
  color: var(--app-text-muted);
  flex: 1;
}

.hr-step-card__meta {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--app-text);
}

.hr-step-card__btn {
  margin-top: var(--app-space-2);
}

.hr-done-banner {
  margin-top: var(--app-space-5);
  border: 1px solid var(--app-border-strong);
  background: var(--app-surface-strong);
}
</style>
