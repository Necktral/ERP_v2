<template>
  <q-page class="q-pa-md">
    <div class="text-h6">Branches</div>
    <div class="text-caption text-grey-7">Listado: requiere <b>org.branch.read</b>.</div>

    <q-card class="q-mt-md">
      <q-card-section>
        <q-btn label="Recargar" flat @click="load" :disable="loading" />
      </q-card-section>

      <q-separator />

      <q-card-section>
        <q-table
          title="Branches"
          :rows="rows"
          :columns="columns"
          row-key="id"
          :loading="loading"
          :rows-per-page-options="[10, 20, 50, 0]"
        />
        <q-banner v-if="errorMsg" class="q-mt-md" dense rounded>
          {{ errorMsg }}
        </q-banner>
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { listBranches, type BranchRow } from 'src/services/org.service';
import { isAxiosError } from 'axios';
import type { QTableColumn } from 'quasar';

const loading = ref(false);
const errorMsg = ref<string | null>(null);
const rows = ref<BranchRow[]>([]);

const columns: QTableColumn[] = [
  { name: 'name', label: 'Name', field: 'name', align: 'left', sortable: true },
  { name: 'code', label: 'Code', field: 'code', align: 'left', sortable: true },
  { name: 'is_active', label: 'Active', field: 'is_active', align: 'left', sortable: true },
  { name: 'address', label: 'Address', field: 'address', align: 'left' },
  { name: 'phone', label: 'Phone', field: 'phone', align: 'left' },
  { name: 'email', label: 'Email', field: 'email', align: 'left' },
];

async function load() {
  loading.value = true;
  errorMsg.value = null;
  try {
    rows.value = await listBranches();
  } catch (e: unknown) {
    errorMsg.value = isAxiosError(e) ? (e.response?.data?.detail ?? e.message) : String(e);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>
