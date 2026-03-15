import { z } from "zod";

const EnvSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  DATABASE_URL: z.url(),
  GOOGLE_CLIENT_ID: z.string().min(1),
  GOOGLE_CLIENT_SECRET: z.string().min(1),
  BETTER_AUTH_SECRET: z.string().min(1),
  BETTER_AUTH_URL: z.url()
});

export type Environment = z.infer<typeof EnvSchema>;

export function parseEnv(data: unknown): Environment {
  const parsed = EnvSchema.safeParse(data);

  if (parsed.success) {
    return parsed.data;
  }

  const tree = z.treeifyError(parsed.error);

  const message = Object.entries(tree.properties ?? {})
    .map(([key, value]) => `${key}: ${value.errors?.join(", ") ?? "Invalid value"}`)
    .join("\n");

  throw new Error(`Invalid environment variables:\n${message}`);
}

export const env = Object.freeze(parseEnv(process.env));