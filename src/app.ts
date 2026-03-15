import createApp from '@/lib/create-app'
import index from '@/routes/index.route'
import auth from '@/routes/auth/auth.index'
import store from '@/routes/store/store.route'
import inventory from '@/routes/inventory/inventory.route'
import khata from '@/routes/khata/khata.route'
import agent from '@/routes/agent/agent.route'

const app = createApp()

const routes = [
  index,
  auth,
  store,
  inventory,
  khata,
  agent,
] as const

routes.forEach((route) => {
  app.route('/', route)
})

export default app
