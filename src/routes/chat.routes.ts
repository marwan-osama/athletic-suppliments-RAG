// src/routes/chat.routes.ts
import { Router } from "express";
import { handleChat } from "../controllers/chat.controller";

const router = Router();
router.post("/chat", handleChat);
export default router;
