/** `node dist/cli.js migrate [--apply] [--confirm --backup FILE]`: see the plan, then apply it. */
import { existsSync, statSync } from "node:fs";

import { loadConfig } from "./config.js";
import { createDb } from "./db.js";
import { applyMigration, isDestructive, planMigration } from "./schema/migrate.js";
import { loadSpec } from "./spec/loader.js";

const args = process.argv.slice(2);
const config = loadConfig();
const db = createDb(config.databaseUrl);
const plan = await planMigration(db, loadSpec(config.specPath));
console.log(JSON.stringify(plan, null, 1));
if (args.includes("--apply")) {
  const backup = args[args.indexOf("--backup") + 1];
  if (isDestructive(plan) && !(args.includes("--backup") && backup && existsSync(backup) && statSync(backup).size > 0)) {
    console.error("This plan destroys data. Pass --confirm and --backup with the path of a real, non-empty dump.");
    process.exitCode = 3;
  } else {
    await applyMigration(db, plan, { confirmDestructive: args.includes("--confirm"), backupReference: backup });
    console.log("applied");
  }
}
await db.destroy();
