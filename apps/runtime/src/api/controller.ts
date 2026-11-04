/** C-7. Thin on purpose: every rule lives in the services, so no route can skip one. */
import { Body, Controller, Delete, Get, HttpCode, Inject, Param, Patch, Post, Query, Req, Res } from "@nestjs/common";
import { parse as parseCookie, serialize } from "cookie";
import type { Request, Response } from "express";

import type { DaftarSpec } from "@daftar/spec/types";

import type { AuthService } from "../auth/service.js";
import type { Config } from "../config.js";
import type { Db } from "../db.js";
import { BadQuery, Forbidden, Unauthorized } from "../errors.js";
import type { User } from "../records/access.js";
import type { ListQuery, RecordService } from "../records/service.js";
import { applyImport, exportWorkbook, startImport } from "./roundtrip.js";
import { auditCsv, metaFor, notificationsFor, processingRegister, runCalculator } from "./features.js";

export const RUNTIME = Symbol("runtime");
export interface Runtime {
  spec: DaftarSpec;
  config: Pick<Config, "timezone" | "processor" | "workerUrl">;
  db: Db;
  auth: AuthService;
  records: RecordService;
  clock: () => Date;
}

const COOKIE = "daftar_session";
const BOM = String.fromCharCode(0xfeff); // So Excel reads the CSV as UTF-8.
const FILTER = /^filter\.([a-z][a-z0-9_]*)(?:\.([a-zA-Z]+))?$/;

function tokenOf(request: Request): string | undefined {
  return parseCookie(request.headers.cookie ?? "")[COOKIE];
}

function listQuery(query: Record<string, unknown>): ListQuery {
  const text = (key: string): string | undefined => (typeof query[key] === "string" ? (query[key]) : undefined);
  const number = (key: string): number | undefined => {
    const value = text(key);
    if (value === undefined) return undefined;
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) throw new BadQuery(key);
    return parsed;
  };
  const filters: NonNullable<ListQuery["filters"]> = [];
  for (const [key, value] of Object.entries(query)) {
    const match = FILTER.exec(key);
    if (match && typeof value === "string") filters.push({ field: match[1] as string, op: match[2] ?? "eq", value });
  }
  return { q: text("q"), sort: text("sort"), page: number("page"), pageSize: number("pageSize"), totals: text("totals"), filters };
}

@Controller("api")
export class ApiController {
  constructor(@Inject(RUNTIME) private readonly runtime: Runtime) {}

  private async user(request: Request): Promise<User> {
    const user = await this.runtime.auth.fromToken(tokenOf(request));
    if (!user) throw new Unauthorized();
    return user;
  }

  private setSession(request: Request, response: Response, token: string, expires: Date): void {
    response.setHeader(
      "Set-Cookie",
      serialize(COOKIE, token, { httpOnly: true, sameSite: "lax", secure: request.secure, path: "/", expires }),
    );
  }

  @Get("auth/status")
  async status(): Promise<{ needsSetup: boolean }> {
    return { needsSetup: await this.runtime.auth.needsSetup() };
  }

  @Post("auth/setup")
  async setup(@Body() body: Record<string, unknown>, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    const { user, token, expires } = await this.runtime.auth.setup(body.username, body.password);
    this.setSession(request, response, token, expires);
    return { username: user.username, role: user.role };
  }

  @Post("auth/login")
  @HttpCode(200)
  async login(@Body() body: Record<string, unknown>, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    const { user, token, expires } = await this.runtime.auth.login(body.username, body.password);
    this.setSession(request, response, token, expires);
    return { username: user.username, role: user.role };
  }

  @Post("auth/logout")
  @HttpCode(204)
  async logout(@Req() request: Request, @Res({ passthrough: true }) response: Response): Promise<void> {
    await this.runtime.auth.logout(tokenOf(request));
    response.setHeader("Set-Cookie", serialize(COOKIE, "", { httpOnly: true, sameSite: "lax", path: "/", maxAge: 0 }));
  }

  @Get("auth/me")
  async me(@Req() request: Request) {
    const user = await this.user(request);
    return { username: user.username, role: user.role };
  }

  @Post("auth/users")
  async createUser(@Body() body: Record<string, unknown>, @Req() request: Request) {
    const created = await this.runtime.auth.createUser(await this.user(request), body.username, body.password, body.role);
    return { username: created.username, role: created.role };
  }

  @Get("meta")
  async meta(@Req() request: Request) {
    return metaFor(this.runtime.spec, await this.user(request));
  }

  @Get("e/:entity")
  async list(@Param("entity") entity: string, @Query() query: Record<string, unknown>, @Req() request: Request) {
    return this.runtime.records.list(await this.user(request), entity, listQuery(query));
  }

  @Post("e/:entity")
  async create(@Param("entity") entity: string, @Body() body: Record<string, unknown>, @Req() request: Request) {
    return this.runtime.records.create(await this.user(request), entity, body);
  }

  @Get("e/:entity/:id")
  async get(@Param("entity") entity: string, @Param("id") id: string, @Req() request: Request) {
    return this.runtime.records.get(await this.user(request), entity, id);
  }

  @Patch("e/:entity/:id")
  async update(@Param("entity") entity: string, @Param("id") id: string, @Body() body: Record<string, unknown>, @Req() request: Request) {
    return this.runtime.records.update(await this.user(request), entity, id, body);
  }

  @Delete("e/:entity/:id")
  @HttpCode(204)
  async remove(@Param("entity") entity: string, @Param("id") id: string, @Req() request: Request): Promise<void> {
    await this.runtime.records.remove(await this.user(request), entity, id);
  }

  @Get("e/:entity/:id/history")
  async history(@Param("entity") entity: string, @Param("id") id: string, @Req() request: Request) {
    return { changes: await this.runtime.records.history(await this.user(request), entity, id) };
  }

  @Post("e/:entity/:id/transition")
  @HttpCode(200)
  async transition(@Param("entity") entity: string, @Param("id") id: string, @Body() body: Record<string, unknown>, @Req() request: Request) {
    return this.runtime.records.transition(await this.user(request), entity, id, String(body.action));
  }

  @Post("changes/:id/revert")
  @HttpCode(204)
  async revert(@Param("id") id: string, @Req() request: Request): Promise<void> {
    await this.runtime.records.revert(await this.user(request), id);
  }

  @Post("batches/:id/undo")
  @HttpCode(200)
  async undo(@Param("id") id: string, @Req() request: Request) {
    return this.runtime.records.undoBatch(await this.user(request), id);
  }

  @Post("calc/:calculator")
  @HttpCode(200)
  async calc(@Param("calculator") calculator: string, @Body() body: Record<string, unknown>, @Req() request: Request) {
    return runCalculator(this.runtime.spec, await this.user(request), calculator, body);
  }

  @Get("register")
  async register(@Req() request: Request) {
    return processingRegister(this.runtime.spec, await this.user(request), this.runtime.config.processor);
  }

  @Get("notifications")
  async notifications(@Req() request: Request) {
    const { db, spec, config, clock } = this.runtime;
    return { notifications: await notificationsFor(db, spec, await this.user(request), config.timezone, clock()) };
  }

  @Get("export.xlsx")
  async exportXlsx(@Query("locale") locale: string | undefined, @Req() request: Request, @Res() response: Response): Promise<void> {
    const user = await this.user(request);
    const { db, spec, config } = this.runtime;
    const data = await exportWorkbook(db, spec, user, config, locale === "ar-DZ" || locale === "fr-DZ" ? locale : undefined);
    response.setHeader("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    response.setHeader("Content-Disposition", 'attachment; filename="daftar.xlsx"');
    response.send(data);
  }

  /** The body is the file itself, so a browser's fetch can send it with no form encoding. */
  @Post("import")
  async startImport(@Query("name") name: string | undefined, @Req() request: Request) {
    const user = await this.user(request);
    const { db, spec, config } = this.runtime;
    const body = request.body as unknown;
    if (!Buffer.isBuffer(body) || !body.length) throw new BadQuery("file");
    return startImport(db, spec, user, config, body, name ?? "import.xlsx");
  }

  @Post("import/:diffId/apply")
  @HttpCode(200)
  async applyImport(@Param("diffId") diffId: string, @Body() body: Record<string, unknown>, @Req() request: Request) {
    const { db, spec, records } = this.runtime;
    return applyImport(db, spec, records, await this.user(request), diffId, body.selected as Parameters<typeof applyImport>[5]);
  }

  /** C-9's compliance export. History is the automated log that Law 25-11 asks for. */
  @Get("audit.csv")
  async audit(@Req() request: Request, @Res() response: Response): Promise<void> {
    const user = await this.user(request);
    if (user.role !== "owner" && user.role !== "accountant") throw new Forbidden();
    const rows = await this.runtime.db.selectFrom("_audit").selectAll().orderBy("seq").execute();
    response.setHeader("Content-Type", "text/csv; charset=utf-8");
    response.setHeader("Content-Disposition", 'attachment; filename="audit.csv"');
    response.send(`${BOM}${auditCsv(rows.map((row) => this.runtime.records.presentAudit(user, row)))}`);
  }
}
