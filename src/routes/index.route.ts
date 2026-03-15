import { createRouter } from '@/lib/create-app'

const router = createRouter()

router.get('/', (c) => {
  return c.json({ message: 'App API' }, 200)
})

export default router
