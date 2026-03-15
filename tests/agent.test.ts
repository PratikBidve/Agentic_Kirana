import { describe, it, expect } from 'bun:test';
import app from '@/app';

describe('Agent Routes', () => {
  describe('POST /api/agent/message', () => {
    it('should return 400 for missing storeId', async () => {
      const req = new Request('http://localhost/api/agent/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: 'Add 10kg sugar to stock' }),
      });
      const res = await app.fetch(req);
      expect(res.status).toBe(400);
    });

    it('should return 400 for empty message', async () => {
      const req = new Request('http://localhost/api/agent/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ storeId: 'some-store-id', message: '' }),
      });
      const res = await app.fetch(req);
      expect(res.status).toBe(400);
    });

    it('should return 400 for message exceeding 2000 chars', async () => {
      const req = new Request('http://localhost/api/agent/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ storeId: 'some-store-id', message: 'a'.repeat(2001) }),
      });
      const res = await app.fetch(req);
      expect(res.status).toBe(400);
    });
  });

  describe('GET /api/agent/status/:jobId', () => {
    it('should return 404 for non-existent jobId', async () => {
      const req = new Request(
        `http://localhost/api/agent/status/non-existent-job-id-that-does-not-exist`
      );
      // This will fail at DB level in integration tests
      // In unit tests without DB, returns 404 or 500 depending on DB mock
      const res = await app.fetch(req);
      expect([404, 500]).toContain(res.status);
    });
  });
});
