// src/controllers/auth.controller.ts
import { Request, Response, NextFunction } from "express";
import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import { prisma } from "../config/db";
import { env } from "../config/env";

// Register a new user
export const register = async (req: Request, res: Response, next: NextFunction) => {
  const { email, password } = req.body;
  if (!email || !password) {
    return res.status(400).json({ error: "Email and password required", code: "INVALID_INPUT" });
  }
  try {
    const existing = await prisma.user.findUnique({ where: { email } });
    if (existing) {
      return res.status(409).json({ error: "Email already registered", code: "EMAIL_EXISTS" });
    }
    const passwordHash = await bcrypt.hash(password, 10);
    const user = await prisma.user.create({ data: { email, passwordHash } });
    // Do not return passwordHash
    res.status(201).json({ id: user.id, email: user.email });
  } catch (err) {
    next(err);
  }
};

// Login and get JWT
export const login = async (req: Request, res: Response, next: NextFunction) => {
  const { email, password } = req.body;
  if (!email || !password) {
    return res.status(400).json({ error: "Email and password required", code: "INVALID_INPUT" });
  }
  try {
    const user = await prisma.user.findUnique({ where: { email } });
    if (!user) {
      return res.status(401).json({ error: "Invalid credentials", code: "INVALID_CREDENTIALS" });
    }
    const valid = await bcrypt.compare(password, user.passwordHash);
    if (!valid) {
      return res.status(401).json({ error: "Invalid credentials", code: "INVALID_CREDENTIALS" });
    }
    const token = jwt.sign({ id: user.id, email: user.email }, env.JWT_SECRET, { expiresIn: "7d" });
    res.json({ token });
  } catch (err) {
    next(err);
  }
};

// Return current user info (protected)
export const me = async (req: Request, res: Response, next: NextFunction) => {
  // auth middleware attaches req.user
  const user = (req as any).user;
  if (!user) {
    return res.status(401).json({ error: "Authentication required", code: "UNAUTHORIZED" });
  }
  try {
    const dbUser = await prisma.user.findUnique({ where: { id: user.id } });
    if (!dbUser) {
      return res.status(404).json({ error: "User not found", code: "USER_NOT_FOUND" });
    }
    res.json({ id: dbUser.id, email: dbUser.email, createdAt: dbUser.createdAt, updatedAt: dbUser.updatedAt });
  } catch (err) {
    next(err);
  }
};
