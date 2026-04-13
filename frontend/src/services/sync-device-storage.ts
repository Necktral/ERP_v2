export type StoredSyncDeviceIdentity = {
  deviceId: string;
  companyId: number;
  branchId: number | null;
  label: string;
  publicKeyB64: string;
  privateKeyPkcs8B64: string;
  createdAt: string;
  updatedAt: string;
};

const DB_NAME = 'necktral_sync_pwa';
const STORE_NAME = 'device_identity';
const ACTIVE_KEY = 'active';

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('No se pudo abrir IndexedDB.'));
  });
}

async function runTx<T>(mode: IDBTransactionMode, fn: (store: IDBObjectStore, done: (value: T) => void) => void): Promise<T> {
  const db = await openDb();
  return await new Promise<T>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, mode);
    const store = tx.objectStore(STORE_NAME);
    fn(store, resolve);
    tx.onerror = () => reject(tx.error ?? new Error('Error de transacción IndexedDB.'));
    tx.oncomplete = () => db.close();
    tx.onabort = () => {
      db.close();
      reject(tx.error ?? new Error('Transacción IndexedDB abortada.'));
    };
  });
}

export async function saveActiveSyncDeviceIdentity(identity: StoredSyncDeviceIdentity): Promise<void> {
  await runTx<void>('readwrite', (store, done) => {
    store.put(identity, ACTIVE_KEY);
    store.transaction.oncomplete = () => done();
  });
}

export async function getActiveSyncDeviceIdentity(): Promise<StoredSyncDeviceIdentity | null> {
  return await runTx<StoredSyncDeviceIdentity | null>('readonly', (store, done) => {
    const req = store.get(ACTIVE_KEY);
    req.onsuccess = () => {
      const value = req.result;
      done(value && typeof value === 'object' ? (value as StoredSyncDeviceIdentity) : null);
    };
    req.onerror = () => done(null);
  });
}
