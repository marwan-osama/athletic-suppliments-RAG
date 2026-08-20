// src/routes/conversation.routes.ts
import { Router } from "express";
import {
  createConversation,
  listConversations,
  getConversation,
  deleteConversation,
  getMessages,
} from "../controllers/conversation.controller";

const router = Router();

router.post("/conversations", createConversation);
router.get("/conversations", listConversations);
router.get("/conversations/:id/messages", getMessages);
router.get("/conversations/:id", getConversation);
router.delete("/conversations/:id", deleteConversation);

export default router;
