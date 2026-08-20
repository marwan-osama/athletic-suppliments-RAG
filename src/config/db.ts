import { PrismaClient } from "@prisma/client";

// Prisma client instance – will lazily connect on first query.
export const prisma = new PrismaClient();
