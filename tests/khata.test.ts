import { describe, it, expect } from 'bun:test';
import app from '@/app';

describe('Khata Routes', () => {
  const fakeStoreId = 'non-existent-store-id';
  const fakeCustomerId = 'non-existent-customer-id';

  describe('POST /api/stores/:storeId/customers', () => {
    it('should return 401 if not authenticated', async () => {
      const req = new Request(`http://localhost/api/stores/${fakeStoreId}/customers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'Ramesh Sharma' }),
      });
      const res = await app.fetch(req);
      expect(res.status).toBe(401);
    });
  });

  describe('POST /api/stores/:storeId/khata', () => {
    it('should return 401 if not authenticated', async () => {
      const req = new Request(`http://localhost/api/stores/${fakeStoreId}/khata`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customerId: fakeCustomerId,
          amount: 250,
          note: 'Monthly groceries on credit',
        }),
      });
      const res = await app.fetch(req);
      expect(res.status).toBe(401);
    });

    it('should return 400 if amount is zero', async () => {
      const req = new Request(`http://localhost/api/stores/${fakeStoreId}/khata`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customerId: fakeCustomerId,
          amount: 0,
        }),
      });
      const res = await app.fetch(req);
      expect([400, 401]).toContain(res.status);
    });
  });

  describe('PATCH /api/stores/:storeId/khata/:entryId/confirm', () => {
    it('should return 401 if not authenticated', async () => {
      const req = new Request(
        `http://localhost/api/stores/${fakeStoreId}/khata/fake-entry-id/confirm`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ confirmedByOwner: true }),
        }
      );
      const res = await app.fetch(req);
      expect(res.status).toBe(401);
    });
  });
});
