// src/server.ts
import app from "./app";
import { env } from "./config/env";

const port = parseInt(env.PORT, 10);

app.listen(port, () => {
  console.log(`Node API listening on http://localhost:${port}`);
});
