/**
 * Documentos (IDP) — escaneo → OCR → extracción de campos → revisión humana.
 * Invariante: extraer JAMÁS integra; integrar es decisión del proceso de negocio.
 */
import { api } from 'src/boot/axios';
import { PAGE } from 'src/core/api';

export const DOC_TYPE_LABELS: Record<string, string> = {
  GENERAL: 'General',
  INVOICE: 'Factura',
  FUEL_TICKET: 'Ticket de combustible',
  PAYROLL: 'Planilla',
  REMISION: 'Remisión',
};

export const SCAN_STATUS_LABELS: Record<string, string> = {
  PENDING_OCR: 'Pendiente de OCR',
  PROCESSED: 'OCR listo',
  EXTRACTED: 'Extraído (por revisar)',
  REVIEWED: 'Revisado',
  FAILED: 'Falló',
};

export interface ScanRow {
  id: number;
  doc_type: string;
  status: string;
  created_at?: string;
  reviewed_by?: number | null;
  extracted_fields?: Record<string, unknown> | null;
  ocr_text?: string;
  [k: string]: unknown;
}

export async function listScans(status?: string): Promise<ScanRow[]> {
  const params: Record<string, string | number> = { ...PAGE };
  if (status) params.status = status;
  const { data } = await api.get<{ results: ScanRow[] }>('/documents/scans/', { params });
  return data.results;
}

export async function getScan(scanId: number): Promise<ScanRow> {
  const { data } = await api.get<ScanRow>(`/documents/scans/${scanId}/`);
  return data;
}

export async function uploadScan(docType: string, imageBase64: string): Promise<ScanRow> {
  const { data } = await api.post<ScanRow>('/documents/scans/upload/', {
    doc_type: docType,
    image_base64: imageBase64,
  });
  return data;
}

export async function extractScan(scanId: number): Promise<ScanRow> {
  const { data } = await api.post<ScanRow>(`/documents/scans/${scanId}/extract/`, {});
  return data;
}

export async function reviewScan(
  scanId: number,
  input: { extracted_fields?: Record<string, unknown>; doc_type?: string },
): Promise<ScanRow> {
  const { data } = await api.post<ScanRow>(`/documents/scans/${scanId}/review/`, input);
  return data;
}
