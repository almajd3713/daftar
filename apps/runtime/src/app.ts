/** Assemble the runtime from a spec and a database. */
import "reflect-metadata";

import { Module, type DynamicModule, type INestApplication } from "@nestjs/common";
import { NestFactory } from "@nestjs/core";
import type { NestExpressApplication } from "@nestjs/platform-express";
import { raw, type NextFunction, type Request, type Response } from "express";

import type { DaftarSpec } from "@daftar/spec/types";

import { ApiController, RUNTIME, type Runtime } from "./api/controller.js";
import { AuthService } from "./auth/service.js";
import type { Config } from "./config.js";
import type { Db } from "./db.js";
import { loadEngine } from "./expr/engine.js";
import { RecordService } from "./records/service.js";
import { migrateOnBoot } from "./schema/migrate.js";
import { loadSeedOnce } from "./seed.js";

@Module({})
class ApiModule {
  static with(runtime: Runtime): DynamicModule {
    return { module: ApiModule, controllers: [ApiController], providers: [{ provide: RUNTIME, useValue: runtime }] };
  }
}

/** A cross-site form can't send JSON, and session cookies are SameSite=Lax. Together, no CSRF. */
function jsonWritesOnly(request: Request, response: Response, next: NextFunction): void {
  const writes = ["POST", "PATCH", "PUT", "DELETE"].includes(request.method);
  // The one route whose body is a file. It needs a session too, and a form can't send this type.
  if (request.method === "POST" && request.path === "/api/import" && request.is(XLSX_TYPES)) {
    next();
    return;
  }
  const hasBody = Number(request.headers["content-length"] ?? 0) > 0;
  if (writes && hasBody && !request.is("application/json")) {
    response.status(415).json({ error: "json_required" });
    return;
  }
  next();
}

const XLSX_TYPES = ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/octet-stream"];
const MAX_UPLOAD = "26mb";

export interface AppOptions {
  spec: DaftarSpec;
  db: Db;
  config: Pick<Config, "secret" | "timezone" | "processor"> & Partial<Pick<Config, "workerUrl">>;
  clock?: () => Date;
  /** The accepted import data (C-8), loaded once on first start. */
  seedDir?: string;
  /** Set only by the Studio's preview. Cookies ignore ports, so it can't share the usual name. */
  previewCookie?: string;
}

export async function createApp(options: AppOptions): Promise<INestApplication> {
  const { spec, db, config } = options;
  const clock = options.clock ?? (() => new Date());
  await loadEngine();
  await migrateOnBoot(db, spec);
  const records = new RecordService(db, spec, clock);
  if (options.seedDir) await loadSeedOnce(db, spec, records, options.seedDir);
  const runtime: Runtime = {
    spec,
    db,
    config: { ...config, workerUrl: config.workerUrl },
    sessionCookie: options.previewCookie ?? "daftar_session",
    preview: options.previewCookie !== undefined,
    clock,
    auth: new AuthService(db, spec, config.secret),
    records,
  };
  const app = await NestFactory.create<NestExpressApplication>(ApiModule.with(runtime), { logger: ["error"] });
  app.set("trust proxy", 1);
  app.disable("x-powered-by");
  app.use(jsonWritesOnly);
  app.use("/api/import", raw({ type: XLSX_TYPES, limit: MAX_UPLOAD }));
  return app;
}
