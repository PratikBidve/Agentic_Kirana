import createApp from '@/lib/create-app'
import index from '@/routes/index.route'
import auth from '@/routes/auth/auth.index'

const app = createApp()

const routes = [
    index,
    auth,
  ] as const;

routes.forEach((route) => {
  app.route('/', route)
})

export default app