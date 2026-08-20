// src/config/env.ts
import dotenv from "dotenv";
import { z } from "zod";

dotenv.config();

const envSchema = z.object({
  PORT: z.string().optional().default("3000"),
  PY_RAG_URL: z.string().url().default("http://localhost:8001"),
  JWT_SECRET: z.string().min(10).default("CHANGE_ME_TO_A_LONG_RANDOM_SECRET"),
  RATE_LIMIT_WINDOW_MS: z.coerce.number().optional().default(60000),
  RATE_LIMIT_MAX_REQUESTS: z.coerce.number().optional().default(30)
});

export const env = envSchema.parse(process.env);
