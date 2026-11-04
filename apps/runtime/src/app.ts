/** Assemble the runtime from a spec and a database. */
import "reflect-metadata";

import { Module, type DynamicModule, type INestApplication } from "@nestjs/common";
import { NestFactory } from "@nestjs/core";
import type { NestExpressApplication } from "@nestjs/platform-express";
import type { NextFunction, Request, Response } from "express";

import type { DaftarSpec } from "@daftar/spec/types";

import { ApiController, RUNTIME, type Runtime } from "./api/controller.js";
import { AuthService } from "./auth/service.js";
import type { Config } from "./config.js";
import type { Db } from "./db.js";
import { loadEngine } from "./expr/engine.js";
import { RecordService } from "./records/service.js";
import { migrateOnBoot } from "./schema/migrate.js";

@Module({})
class ApiModule {
  static with(runtime: Runtime): DynamicModule {
    return { module: ApiModule, controllers: [ApiController], providers: [{ provide: RUNTIME, useValue: runtime }] };
  }
}

/** A cross-site form can't send JSON, and session cookies are SameSite=Lax. Together, no CSRF. */
function jsonWritesOnly(request: Request, response: Response, next: NextFunction): void {
  const writes = ["POST", "PATCH", "PUT", "DELETE"].includes(request.method);
  const hasBody = Number(request.headers["content-length"] ?? 0) > 0;
  if (writes && hasBody && !request.is("application/json")) {
    response.status(415).json({ error: "json_required" });
    return;
  }
  next();
}

export interface AppOptions {
  spec: DaftarSpec;
  db: Db;
  config: Pick<Config, "secret" | "timezone" | "processor">;
  clock?: () => Date;
}

export async function createApp(options: AppOptions): Promise<INestApplication> {
  const { spec, db, config } = options;
  const clock = options.clock ?? (() => new Date());
  await loadEngine();
  await migrateOnBoot(db, spec);
  const runtime: Runtime = {
    spec,
    db,
    config,
    clock,
    auth: new AuthService(db, spec, config.secret),
    records: new RecordService(db, spec, clock),
  };
  const app = await NestFactory.create<NestExpressApplication>(ApiModule.with(runtime), { logger: ["error"] });
  app.set("trust proxy", 1);
  app.disable("x-powered-by");
  app.use(jsonWritesOnly);
  return app;
}
