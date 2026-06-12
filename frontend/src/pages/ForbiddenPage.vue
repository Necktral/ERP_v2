<template>
  <q-page class="fb-page">
    <div class="fb-card app-fade-up">
      <q-icon name="lock" size="42px" class="fb-icon" />
      <div class="fb-code">403</div>
      <div class="fb-text">No tenés permiso para entrar aquí con tu rol actual.</div>
      <div class="fb-hint">Si creés que deberías tener acceso, pedíselo al administrador de tu empresa.</div>
      <div class="fb-actions">
        <q-btn unelevated no-caps color="primary" icon="home" label="Ir al inicio" to="/" />
        <q-btn flat no-caps icon="swap_horiz" label="Cambiar de empresa" to="/select-context" />
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
//
</script>

<style scoped>
.fb-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--app-space-4);
  background: var(--app-bg-gradient);
  background-color: var(--app-bg);
}

.fb-card {
  width: 100%;
  max-width: 420px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--app-space-3);
  text-align: center;
  padding: var(--app-space-8) var(--app-space-6);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
  box-shadow: var(--app-shadow-card);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.fb-icon {
  opacity: 0.5;
}

.fb-code {
  font-size: 2.4rem;
  font-weight: 700;
  line-height: 1;
}

.fb-text {
  font-weight: 500;
}

.fb-hint {
  font-size: 0.8rem;
  opacity: 0.7;
}

.fb-actions {
  display: flex;
  gap: var(--app-space-3);
  margin-top: var(--app-space-3);
  flex-wrap: wrap;
  justify-content: center;
}
</style>
