/**
 * Inventario (kernel inventarios) — bodegas, artículos, lotes, existencias,
 * kardex y movimientos (recibir/despachar/ajustar/transferir).
 *
 * Los movimientos generan idempotency_key (uuid) para que un reintento de red
 * no duplique el movimiento. El backend responde con el saldo y el estado
 * contable (accounting_status) del posteo automático a GL.
 */
import { api } from 'src/boot/axios';
import { PAGE, type Paginated } from 'src/core/api';

// --- Catálogos / enums --------------------------------------------------------
export const UOM_LABELS: Record<string, string> = {
  UNIT: 'Unidad',
  DOZEN: 'Docena',
  PACK: 'Paquete',
  BOX: 'Caja',
  GRAM: 'Gramo',
  KILOGRAM: 'Kilogramo',
  POUND: 'Libra',
  QUINTAL: 'Quintal (100 lb)',
  TON: 'Tonelada métrica',
  MILLILITER: 'Mililitro',
  LITER: 'Litro',
  GALLON: 'Galón',
  BARREL: 'Barril',
  METER: 'Metro',
  SQUARE_METER: 'Metro cuadrado',
  MANZANA: 'Manzana',
  HOUR: 'Hora',
  DAY: 'Día',
  GOLD_QUINTAL: 'Quintal oro',
  WET_QUINTAL: 'Quintal húmedo',
  DRY_QUINTAL: 'Quintal seco',
};

export const WAREHOUSE_TYPE_LABELS: Record<string, string> = {
  GENERAL: 'General',
  AGROCHEMICAL: 'Agroquímicos',
  COLD_STORAGE: 'Cámara fría',
  FINISHED_GOODS: 'Producto terminado',
  RAW_MATERIALS: 'Materia prima',
  TOOLS: 'Herramientas y equipos',
  FUEL: 'Combustibles',
  TRANSIT: 'En tránsito',
  COFFEE: 'Café',
};

export const MOVEMENT_TYPE_LABELS: Record<string, string> = {
  RECEIVE: 'Recepción',
  ISSUE: 'Despacho',
  ADJUST: 'Ajuste',
  TRANSFER_OUT: 'Transferencia (salida)',
  TRANSFER_IN: 'Transferencia (entrada)',
  RETURN: 'Devolución',
  SHRINKAGE: 'Merma',
  PRODUCTION_IN: 'Producción (entrada)',
  PRODUCTION_OUT: 'Producción (salida)',
  PHYSICAL_COUNT: 'Conteo físico',
};

// --- Tipos ---------------------------------------------------------------------
export interface Warehouse {
  id: number;
  name: string;
  code: string;
  warehouse_type: string;
  location_description: string;
  is_active: boolean;
  is_default: boolean;
}

export interface InventoryItem {
  id: number;
  sku: string;
  name: string;
  description: string;
  category: string;
  barcode: string;
  uom: string;
  reorder_point: string;
  min_stock_qty: string;
  max_stock_qty: string | null;
  track_lots: boolean;
  track_expiry: boolean;
  shelf_life_days: number | null;
  storage_condition: string;
  is_controlled: boolean;
  is_active: boolean;
}

export interface ItemLot {
  id: number;
  lot_number: string;
  supplier_lot_ref: string;
  production_date: string | null;
  expiry_date: string | null;
  status: string;
  qty_received: string;
  notes: string;
  is_expired: boolean;
  days_to_expiry: number | null;
}

export interface StockRow {
  id: number;
  item: number;
  item_sku: string;
  item_name: string;
  item_uom: string;
  warehouse: number;
  warehouse_name: string;
  qty_on_hand: string;
  qty_reserved: string;
  qty_available: string;
  avg_cost: string;
  updated_at: string;
}

export interface LotStockRow {
  id: number;
  lot: number;
  lot_number: string;
  expiry_date: string | null;
  lot_status: string;
  qty_on_hand: string;
  avg_cost: string;
}

export interface KardexRow {
  id: number;
  movement_type: string;
  item: number;
  item_sku: string;
  warehouse: number;
  warehouse_name: string;
  qty_delta: string;
  unit_cost: string;
  total_cost: string;
  lot: number | null;
  lot_number: string | null;
  note: string;
  accounting_status: string;
  created_at: string;
}

/** Respuesta de cada movimiento posteado (incluye estado del asiento a GL). */
export interface PostResult {
  movement_id: number;
  qty_on_hand: string;
  avg_cost: string;
  accounting_status: string;
  accounting_error: string;
  journal_draft_id: number | null;
  journal_entry_id: number | null;
}

// --- Bodegas ---------------------------------------------------------------------
export async function listWarehouses(): Promise<Warehouse[]> {
  const { data } = await api.get<Paginated<Warehouse>>('/inventory/warehouses/', { params: PAGE });
  return data.results;
}

export async function createWarehouse(input: {
  name: string;
  code?: string;
  warehouse_type?: string;
  location_description?: string;
  is_default?: boolean;
}): Promise<Warehouse> {
  const { data } = await api.post<Warehouse>('/inventory/warehouses/', input);
  return data;
}

// --- Artículos ---------------------------------------------------------------------
export async function listItems(filters: { search?: string; is_active?: boolean } = {}): Promise<
  InventoryItem[]
> {
  const params: Record<string, string | number | boolean> = { ...PAGE };
  if (filters.search) params.search = filters.search;
  if (filters.is_active !== undefined) params.is_active = filters.is_active;
  const { data } = await api.get<Paginated<InventoryItem>>('/inventory/items/', { params });
  return data.results;
}

export interface ItemInput {
  sku: string;
  name: string;
  description?: string;
  category?: string;
  barcode?: string;
  uom?: string;
  reorder_point?: string;
  track_lots?: boolean;
  track_expiry?: boolean;
  shelf_life_days?: number | null;
  is_controlled?: boolean;
}

export async function createItem(input: ItemInput): Promise<InventoryItem> {
  const { data } = await api.post<InventoryItem>('/inventory/items/', input);
  return data;
}

// --- Lotes ---------------------------------------------------------------------
export async function listLots(itemId: number): Promise<ItemLot[]> {
  const { data } = await api.get<Paginated<ItemLot>>('/inventory/lots/', {
    params: { ...PAGE, item_id: itemId },
  });
  return data.results;
}

export async function createLot(input: {
  item_id: number;
  lot_number: string;
  supplier_lot_ref?: string;
  production_date?: string;
  expiry_date?: string;
  notes?: string;
}): Promise<ItemLot> {
  const { data } = await api.post<ItemLot>('/inventory/lots/create/', input);
  return data;
}

// --- Existencias / kardex ---------------------------------------------------------
export async function getStock(filters: {
  warehouse_id?: number;
  item_id?: number;
  below_reorder?: boolean;
} = {}): Promise<StockRow[]> {
  const params: Record<string, string | number | boolean> = { ...PAGE };
  if (filters.warehouse_id) params.warehouse_id = filters.warehouse_id;
  if (filters.item_id) params.item_id = filters.item_id;
  if (filters.below_reorder) params.below_reorder = 'true';
  const { data } = await api.get<Paginated<StockRow>>('/inventory/stock/', { params });
  return data.results;
}

export async function getStockLots(itemId: number, warehouseId?: number): Promise<LotStockRow[]> {
  const params: Record<string, string | number> = { ...PAGE, item_id: itemId };
  if (warehouseId) params.warehouse_id = warehouseId;
  const { data } = await api.get<Paginated<LotStockRow>>('/inventory/stock/lots/', { params });
  return data.results;
}

export async function getKardex(filters: {
  item_id: number;
  warehouse_id?: number;
  movement_type?: string;
  date_from?: string;
  date_to?: string;
}): Promise<KardexRow[]> {
  const params: Record<string, string | number> = { ...PAGE, ...filters };
  const { data } = await api.get<Paginated<KardexRow>>('/inventory/kardex/', { params });
  return data.results;
}

// --- Movimientos ---------------------------------------------------------------------
function idemKey(): string {
  return crypto.randomUUID();
}

export async function receiveStock(input: {
  warehouse_id: number;
  item_id: number;
  qty: string;
  unit_cost: string;
  lot_number?: string;
  expiry_date?: string;
  note?: string;
}): Promise<PostResult> {
  const { data } = await api.post<PostResult>('/inventory/movements/receive/', {
    ...input,
    idempotency_key: idemKey(),
  });
  return data;
}

export async function issueStock(input: {
  warehouse_id: number;
  item_id: number;
  qty: string;
  lot_id?: number;
  note?: string;
}): Promise<PostResult> {
  const { data } = await api.post<PostResult>('/inventory/movements/issue/', {
    ...input,
    idempotency_key: idemKey(),
  });
  return data;
}

export async function adjustStock(input: {
  warehouse_id: number;
  item_id: number;
  new_qty_on_hand: string;
  note?: string;
}): Promise<PostResult> {
  const { data } = await api.post<PostResult>('/inventory/movements/adjust/', {
    ...input,
    idempotency_key: idemKey(),
  });
  return data;
}

export async function transferStock(input: {
  from_warehouse_id: number;
  to_warehouse_id: number;
  item_id: number;
  qty: string;
  lot_id?: number;
  note?: string;
}): Promise<{ from_movement: PostResult; to_movement: PostResult }> {
  const { data } = await api.post<{ from_movement: PostResult; to_movement: PostResult }>(
    '/inventory/transfers/',
    { ...input, idempotency_key: idemKey() },
  );
  return data;
}
