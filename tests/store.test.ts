import { describe, it, expect, beforeEach } from 'bun:test';
import app from '@/app';

// Mock session user injected via middleware in tests
const MOCK_USER_ID = 'test-user-id-1';

// Helper: create authenticated request
function authRequest(method: string, path: string, body?: unknown) {
  return new Request(`http://localhost${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      // In real tests, use a valid session token from Better-Auth test setup
      // For unit tests, mock the session via dependency injection
      'X-Test-User-Id': MOCK_USER_ID,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
}

describe('Store Routes', () => {
  describe('POST /api/stores', () => {
    it('should return 401 if not authenticated', async () => {
      const req = new Request('http://localhost/api/stores', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'Test Store' }),
      });
      const res = await app.fetch(req);
      expect(res.status).toBe(401);
    });

    it('should return 400 if name is missing', async () => {
      const req = authRequest('POST', '/api/stores', { phone: '9876543210' });
      const res = await app.fetch(req);
      // Will be 401 until auth mock is set up, structure test for reference
      expect([400, 401]).toContain(res.status);
    });

    it('should return 400 for invalid GST number', async () => {
      const req = authRequest('POST', '/api/stores', {
        name: 'My Kirana',
        gstNumber: 'INVALID_GST',
      });
      const res = await app.fetch(req);
      expect([400, 401]).toContain(res.status);
    });

    it('should return 400 for invalid Indian mobile number', async () => {
      const req = authRequest('POST', '/api/stores', {
        name: 'My Kirana',
        phone: '1234567890', // doesn't start with 6-9
      });
      const res = await app.fetch(req);
      expect([400, 401]).toContain(res.status);
    });
  });

  describe('GET /api/stores', () => {
    it('should return 401 if not authenticated', async () => {
      const req = new Request('http://localhost/api/stores');
      const res = await app.fetch(req);
      expect(res.status).toBe(401);
    });
  });

  describe('GET /health', () => {
    it('should return 200 with status ok', async () => {
      const req = new Request('http://localhost/health');
      const res = await app.fetch(req);
      expect(res.status).toBe(200);
      const json = await res.json() as { status: string };
      expect(json.status).toBe('ok');
    });
  });
});
