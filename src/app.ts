// src/app.ts
import express, { Request, Response, NextFunction } from "express";
import cors from "cors";
import chatRouter from "./routes/chat.routes";
import healthRouter from "./routes/health.routes";
import authRouter from "./routes/auth.routes";
import conversationRouter from "./routes/conversation.routes";
import { authenticate } from "./middleware/auth";
import { rateLimitMiddleware } from "./middleware/rateLimit";

const app = express();

// Enable CORS – permissive for mobile dev
app.use(cors());

app.use(express.json());

// Global rate limiting (applies to all routes)
app.use(rateLimitMiddleware);

// Public routes
app.use("/health", healthRouter);
app.use("/api/v1/auth", authRouter);

// Protected routes – require valid JWT
app.use("/api/v1", authenticate, chatRouter);
app.use("/api/v1", authenticate, conversationRouter);

// Fallback for unknown routes
app.use((_req: Request, res: Response) => {
  res.status(404).json({ error: "Not found", code: "NOT_FOUND" });
});

// Global error handler
app.use((err: any, _req: Request, res: Response, _next: NextFunction) => {
  console.error(err);
  res.status(500).json({ error: "Internal server error", code: "SERVER_ERROR" });
});

export default app;
