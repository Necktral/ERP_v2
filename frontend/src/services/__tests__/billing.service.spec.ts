import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('src/boot/axios', () => ({ api }));

import {
  createBillingDoc,
  getBillingDocDetail,
  issueBillingDoc,
  listBillingDocs,
  voidBillingDoc,
} from 'src/services/billing.service';

describe('billing.service', () => {
  beforeEach(() => {
    api.get.mockReset();
    api.post.mockReset();
  });

  it('serializa filtros avanzados al listar documentos', async () => {
    api.get.mockResolvedValueOnce({
      data: { count: 0, limit: 20, offset: 0, results: [] },
    });

    await listBillingDocs({
      limit: 20,
      offset: 40,
      status: 'ISSUED',
      doc_type: 'INVOICE',
      q: 'ABC-123',
      date_from: '2026-04-01',
      date_to: '2026-04-16',
      ordering: '-total',
    });

    expect(api.get).toHaveBeenCalledWith('/billing/docs/', {
      params: {
        limit: 20,
        offset: 40,
        status: 'ISSUED',
        doc_type: 'INVOICE',
        q: 'ABC-123',
        date_from: '2026-04-01',
        date_to: '2026-04-16',
        ordering: '-total',
      },
    });
  });

  it('consulta detalle por id', async () => {
    api.get.mockResolvedValueOnce({ data: { id: 10, lines: [] } });

    await getBillingDocDetail(10);

    expect(api.get).toHaveBeenCalledWith('/billing/docs/10/');
  });

  it('crea, emite y anula documento en endpoints canónicos', async () => {
    api.post.mockResolvedValueOnce({ data: { id: 25 } });
    api.post.mockResolvedValueOnce({ data: { ok: true } });
    api.post.mockResolvedValueOnce({ data: { ok: true } });

    await createBillingDoc({
      doc_type: 'INVOICE',
      lines: [{ description: 'Servicio', quantity: '1.0000', unit_price: '5.000000' }],
    });
    await issueBillingDoc(25, { apply_inventory: false, print_after_issue: false });
    await voidBillingDoc(25, { reason: 'Cliente canceló' });

    expect(api.post).toHaveBeenNthCalledWith(1, '/billing/docs/', {
      doc_type: 'INVOICE',
      lines: [{ description: 'Servicio', quantity: '1.0000', unit_price: '5.000000' }],
    });
    expect(api.post).toHaveBeenNthCalledWith(2, '/billing/docs/25/issue/', {
      apply_inventory: false,
      print_after_issue: false,
    });
    expect(api.post).toHaveBeenNthCalledWith(3, '/billing/docs/25/void/', {
      reason: 'Cliente canceló',
    });
  });
});
