// src/middleware/rateLimit.ts
import { Request, Response, NextFunction } from "express";
import { env } from "../config/env";

interface RateLimitEntry {
  count: number;
  windowStart: number;
}

// In-memory store: key → { count, windowStart }
// Key is IP address (per-IP rate limiting)
const store = new Map<string, RateLimitEntry>();

export const rateLimitMiddleware = (req: Request, res: Response, next: NextFunction) => {
  const key = req.ip ?? "unknown";
  const now = Date.now();
  const windowMs = env.RATE_LIMIT_WINDOW_MS;
  const maxRequests = env.RATE_LIMIT_MAX_REQUESTS;

  const entry = store.get(key);

  if (!entry || now - entry.windowStart > windowMs) {
    // New window
    store.set(key, { count: 1, windowStart: now });
    return next();
  }

  entry.count += 1;

  if (entry.count > maxRequests) {
    return res.status(429).json({
      error: "Too many requests",
      code: "RATE_LIMIT_EXCEEDED",
    });
  }

  next();
};
