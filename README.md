# Better-Hono

### Hono + Better-Auth + Drizzle + Cloudflare Workers

A minimal template to kickstart projects with:

- **Hono** – Fast web framework
- **Better Auth** – Authentication system
- **Drizzle ORM** – Database management
- **Cloudflare Workers** – Edge deployment
- **Bun** – Fast JavaScript runtime
- **Docker** – Local database development

Clean setup for authentication, database, and deployment.


## Getting Started

1. **Clone the repository:**

```bash
git clone https://github.com/alwaysnomads/better-hono.git
cd better-hono
```

2. **Install dependencies:**

```bash
bun install
```

3. **Setup your environment:**

```bash
# Copy the example environment file into .env and .dev.vars
cp .env.example .env .dev.vars
```

- **.env**: Used by your application (e.g., in Drizzle).
- **.dev.vars**: Used by Wrangler when running the local server.

> Edit both files with your environment variables.

4. **Start the database (if needed):**

```bash
# Start the local Postgres database with Docker
bun run docker:up
```

> Or connect to a cloud database like [Neon](https://neon.tech/).  
> Make sure your `.env` and `.dev.vars` point to the correct database URL.

5. **Push database schema and generate types:**

```bash
bun run db:push
bun run db:generate
```

6. **Start the development server:**

```bash
bun run dev
```

> The development server runs on port **3000** by default for easier integration with Better-Auth, you can change it at the wrangler.jsonc file.
> OpenAPI documentation for Better-Auth is available at [http://localhost:3000/api/auth/reference](http://localhost:3000/api/auth/reference).  
> You can remove the OpenAPI plugin if not needed by editing `src/lib/auth.ts`.


## Thanks to w3cj!

This template is heavily inspired by [w3cj's hono-open-api-starter](https://github.com/w3cj/hono-open-api-starter), even using parts of their code. Make sure to check out their repository!


## Available Commands

| Command               | Description                          |
| --------------------- | ------------------------------------ |
| `bun run dev`          | Start local server (Wrangler)        |
| `bun run deploy`       | Deploy to Cloudflare                 |
| `bun run cf-typegen`   | Generate Cloudflare types            |
| `bun run docker:up`    | Start Docker containers              |
| `bun run docker:down`  | Stop Docker containers               |
| `bun run docker:clean` | Stop and remove containers + volumes |
| `bun run db:push`      | Push schema to database              |
| `bun run db:generate`  | Generate Drizzle ORM types           |
| `bun run db:migrate`   | Run database migrations              |
| `bun run db:studio`    | Open Drizzle Studio GUI              |

## Configure template

### Adding New Bindings

To add Cloudflare bindings (e.g., R2 buckets, KV stores), update the bindings types at `src/lib/types.ts`


### Configure Auth

This template comes with Google social login preconfigured for example purposes.  
You can easily change or extend it in `src/lib/auth.ts`.


## License

Released under the [MIT License](LICENSE).

---

✅ Built with **Bun**  
✅ Powered by **Cloudflare Workers**  
✅ Local database ready with **Docker**


