// src/controllers/conversation.controller.ts
import { Request, Response, NextFunction } from "express";
import { prisma } from "../config/db";

// POST /api/v1/conversations
export const createConversation = async (req: Request, res: Response, next: NextFunction) => {
  const userId = req.user!.id;
  const { title } = req.body;
  try {
    const conversation = await prisma.conversation.create({
      data: { userId, title: title ?? "New Conversation" },
    });
    res.status(201).json(conversation);
  } catch (err) {
    next(err);
  }
};

// GET /api/v1/conversations
export const listConversations = async (req: Request, res: Response, next: NextFunction) => {
  const userId = req.user!.id;
  try {
    const conversations = await prisma.conversation.findMany({
      where: { userId },
      orderBy: { updatedAt: "desc" },
    });
    res.json(conversations);
  } catch (err) {
    next(err);
  }
};

// GET /api/v1/conversations/:id
export const getConversation = async (req: Request, res: Response, next: NextFunction) => {
  const userId = req.user!.id;
  const { id } = req.params;
  try {
    const conversation = await prisma.conversation.findFirst({
      where: { id, userId },
    });
    if (!conversation) {
      return res.status(404).json({ error: "Conversation not found", code: "NOT_FOUND" });
    }
    res.json(conversation);
  } catch (err) {
    next(err);
  }
};

// DELETE /api/v1/conversations/:id
export const deleteConversation = async (req: Request, res: Response, next: NextFunction) => {
  const userId = req.user!.id;
  const { id } = req.params;
  try {
    const existing = await prisma.conversation.findFirst({ where: { id, userId } });
    if (!existing) {
      return res.status(404).json({ error: "Conversation not found", code: "NOT_FOUND" });
    }
    // Delete messages first (cascade manually since SQLite may not cascade)
    await prisma.message.deleteMany({ where: { conversationId: id } });
    await prisma.conversation.delete({ where: { id } });
    res.status(204).send();
  } catch (err) {
    next(err);
  }
};

// GET /api/v1/conversations/:id/messages
export const getMessages = async (req: Request, res: Response, next: NextFunction) => {
  const userId = req.user!.id;
  const { id } = req.params;
  try {
    // Verify ownership
    const conversation = await prisma.conversation.findFirst({ where: { id, userId } });
    if (!conversation) {
      return res.status(404).json({ error: "Conversation not found", code: "NOT_FOUND" });
    }
    const messages = await prisma.message.findMany({
      where: { conversationId: id },
      orderBy: { createdAt: "asc" },
    });
    res.json(messages);
  } catch (err) {
    next(err);
  }
};
