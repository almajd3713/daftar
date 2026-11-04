import { createApp } from "./app.js";
import { loadConfig } from "./config.js";
import { createDb } from "./db.js";
import { loadSpec } from "./spec/loader.js";

const config = loadConfig();
const spec = loadSpec(config.specPath);
const app = await createApp({ spec, db: createDb(config.databaseUrl), config });
await app.listen(Number(process.env.PORT ?? 3000), "0.0.0.0");
