import { existsSync } from "node:fs";
import { dirname, join } from "node:path";

import { createApp } from "./app.js";
import { loadConfig } from "./config.js";
import { createDb } from "./db.js";
import { loadSpec } from "./spec/loader.js";
import { findUiDir } from "./ui.js";

const config = loadConfig();
const spec = loadSpec(config.specPath);
const seedDir = join(dirname(config.specPath), "seed");
const app = await createApp({ spec, db: createDb(config.databaseUrl), config, seedDir: existsSync(seedDir) ? seedDir : undefined, uiDir: findUiDir() });
await app.listen(Number(process.env.PORT ?? 3000), "0.0.0.0");
