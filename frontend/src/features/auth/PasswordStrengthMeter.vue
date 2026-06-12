<template>
  <!-- Nivel de confianza: barra en degradado rojo (mala) → verde (buena) + checklist -->
  <div v-if="password" class="q-mt-xs">
    <q-linear-progress
      :value="strength.ratio"
      :color="strength.color"
      track-color="grey-4"
      size="8px"
      rounded
    />
    <div class="row items-center q-mt-xs">
      <q-icon :name="strength.icon" :color="strength.color" size="16px" />
      <span class="text-caption q-ml-xs" :class="`text-${strength.color}`">
        {{ strength.label }}
      </span>
    </div>
    <div class="row q-gutter-x-md q-mt-xs">
      <span
        v-for="check in checks"
        :key="check.key"
        class="text-caption"
        :class="check.ok ? 'text-positive' : 'text-grey-6'"
      >
        <q-icon :name="check.ok ? 'check_circle' : 'radio_button_unchecked'" size="14px" />
        {{ check.label }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { PasswordCheck, PasswordStrength } from 'src/features/auth/usePasswordStrength';

defineProps<{
  password: string;
  checks: PasswordCheck[];
  strength: PasswordStrength;
}>();
</script>
