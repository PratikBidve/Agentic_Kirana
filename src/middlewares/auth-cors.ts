import { cors } from 'hono/cors';

// In production set ALLOWED_ORIGIN env var to your frontend URL
const allowedOrigin = process.env.ALLOWED_ORIGIN ?? 'http://localhost:3000';

export default cors({
  origin: allowedOrigin,
  allowHeaders: ['Content-Type', 'Authorization'],
  allowMethods: ['POST', 'GET', 'PUT', 'DELETE', 'OPTIONS'],
  exposeHeaders: ['Content-Length', 'X-Request-Id'],
  maxAge: 600,
  credentials: true,
});
