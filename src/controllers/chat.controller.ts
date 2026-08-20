// src/controllers/chat.controller.ts
import axios from "axios";
import { Request, Response, NextFunction } from "express";
import { env } from "../config/env";
import { prisma } from "../config/db";

export const handleChat = async (req: Request, res: Response, next: NextFunction) => {
  const userId = req.user!.id;
  const { question, top_k, conversation_id } = req.body;

  // Validate top_k if provided
  if (top_k !== undefined && (typeof top_k !== "number" || top_k <= 0)) {
    return res.status(400).json({ error: "top_k must be a positive integer", code: "INVALID_INPUT" });
  }

  // Validate question
  if (!question || typeof question !== "string" || !question.trim()) {
    return res.status(400).json({ error: "question is required and must be non-empty", code: "INVALID_INPUT" });
  }

  // Verify conversation ownership if provided
  if (conversation_id) {
    const conv = await prisma.conversation.findFirst({ where: { id: conversation_id, userId } });
    if (!conv) {
      return res.status(404).json({ error: "Conversation not found", code: "NOT_FOUND" });
    }
  }

  try {
    const pyResponse = await axios.post(
      `${env.PY_RAG_URL}/api/v1/chat`,
      { question: question.trim(), top_k },
      { timeout: 60000 }
    );
    const { answer, sources } = pyResponse.data;

    // Persist messages if conversation_id provided
    if (conversation_id) {
      await prisma.message.create({ data: { conversationId: conversation_id, role: "user", content: question.trim() } });
      await prisma.message.create({ data: { conversationId: conversation_id, role: "assistant", content: answer } });
      // Update conversation timestamp
      await prisma.conversation.update({ where: { id: conversation_id }, data: { updatedAt: new Date() } });
    }

    res.json({ answer, sources, conversation_id: conversation_id ?? null });
  } catch (err: any) {
    if (err.code === "ECONNREFUSED" || err.code === "ENOTFOUND") {
      return res.status(503).json({ error: "RAG service unavailable", code: "RAG_UNAVAILABLE" });
    }
    const status = err.response?.status ?? 500;
    const data = err.response?.data ?? { error: "RAG error", code: "RAG_ERROR" };
    res.status(status).json(data);
  }
};
