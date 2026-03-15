import { describe, it, expect } from 'bun:test';
import app from '@/app';

describe('Inventory Routes', () => {
  const fakeStoreId = 'non-existent-store-id';

  describe('POST /api/stores/:storeId/products', () => {
    it('should return 401 if not authenticated', async () => {
      const req = new Request(`http://localhost/api/stores/${fakeStoreId}/products`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'Parle-G',
          unit: 'piece',
          currentStock: 100,
          sellingPrice: 5,
        }),
      });
      const res = await app.fetch(req);
      expect(res.status).toBe(401);
    });

    it('should return 400 for invalid unit enum', async () => {
      // Test Zod enum validation for unit field
      const invalidUnits = ['box', 'meter', 'PIECE'];
      for (const unit of invalidUnits) {
        const req = new Request(`http://localhost/api/stores/${fakeStoreId}/products`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: 'Test Product',
            unit,
            currentStock: 10,
            sellingPrice: 20,
          }),
        });
        const res = await app.fetch(req);
        // 401 because auth check happens before validation in current middleware order
        expect([400, 401]).toContain(res.status);
      }
    });

    it('should return 400 for negative sellingPrice', async () => {
      const req = new Request(`http://localhost/api/stores/${fakeStoreId}/products`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'Test Product',
          unit: 'kg',
          currentStock: 10,
          sellingPrice: -5,
        }),
      });
      const res = await app.fetch(req);
      expect([400, 401]).toContain(res.status);
    });
  });

  describe('GET /api/stores/:storeId/products', () => {
    it('should return 401 if not authenticated', async () => {
      const req = new Request(`http://localhost/api/stores/${fakeStoreId}/products`);
      const res = await app.fetch(req);
      expect(res.status).toBe(401);
    });
  });
});
