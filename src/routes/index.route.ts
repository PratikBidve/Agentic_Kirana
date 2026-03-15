import { createRouter } from '@/lib/create-app'

const router = createRouter()

router.get('/', (c) => {
  return c.json({
    name: 'Agentic Kirana API',
    version: '1.0.0',
    status: 'ok',
    docs: '/api/auth/reference',
    timestamp: new Date().toISOString(),
  }, 200)
})

router.get('/health', (c) => {
  return c.json({ status: 'ok', timestamp: new Date().toISOString() }, 200)
})

export default router
