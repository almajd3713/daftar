/** Local accounts and session cookies (D-10). The first account is the owner, with no default credentials. */
import { createHmac, randomBytes } from "node:crypto";

import { hash, verify } from "@node-rs/argon2";
import { sql } from "kysely";

import type { DaftarSpec } from "@daftar/spec/types";

import type { Db } from "../db.js";
import { Conflict, FieldErrors, Forbidden, MESSAGES, Unauthorized } from "../errors.js";
import type { User } from "../records/access.js";

const SESSION_DAYS = 14;
const MIN_PASSWORD = 10;
const MAX_ATTEMPTS = 5;
const ATTEMPT_WINDOW_MS = 15 * 60 * 1000;
// Compared when the username doesn't exist, so timing doesn't reveal which usernames are real.
const DUMMY_HASH = "$argon2id$v=19$m=19456,t=2,p=1$c29tZXNhbHRzb21lc2FsdA$J8ZyYQhJrFpC1aLZqvpt+8kOD0F0FhkTlTiZQ4P3cDg";

export class AuthService {
  private readonly attempts = new Map<string, { count: number; until: number }>();

  constructor(
    private readonly db: Db,
    private readonly spec: DaftarSpec,
    private readonly secret: string,
  ) {}

  private tokenHash(token: string): string {
    return createHmac("sha256", this.secret).update(token).digest("hex");
  }

  private async newSession(userId: string): Promise<{ token: string; expires: Date }> {
    const token = randomBytes(32).toString("base64url");
    const expires = new Date(Date.now() + SESSION_DAYS * 86_400_000);
    await this.db.insertInto("_sessions").values({ token_hash: this.tokenHash(token), user_id: userId, expires_at: expires }).execute();
    return { token, expires };
  }

  private checkCredentials(username: unknown, password: unknown): { username: string; password: string } {
    const errors: Record<string, { fr: string; ar: string }> = {};
    if (typeof username !== "string" || !username.trim()) errors.username = MESSAGES.required;
    if (typeof password !== "string" || password.length < MIN_PASSWORD) errors.password = MESSAGES.weakPassword;
    if (Object.keys(errors).length) throw new FieldErrors(errors);
    return { username: (username as string).trim(), password: password as string };
  }

  async needsSetup(): Promise<boolean> {
    return !(await this.db.selectFrom("_users").select("id").limit(1).executeTakeFirst());
  }

  /** First start: the owner creates their account. Only ever once. */
  async setup(username: unknown, password: unknown): Promise<{ user: User; token: string; expires: Date }> {
    const credentials = this.checkCredentials(username, password);
    const passwordHash = await hash(credentials.password);
    const user = await this.db.transaction().execute(async (tx) => {
      // Two people opening the page at once must not both become the owner.
      await sql`SELECT pg_advisory_xact_lock(20261104)`.execute(tx);
      if (await tx.selectFrom("_users").select("id").limit(1).executeTakeFirst()) throw new Conflict(MESSAGES.setupDone);
      return tx.insertInto("_users").values({ username: credentials.username, password_hash: passwordHash, role: "owner" }).returning(["id", "username", "role"]).executeTakeFirstOrThrow();
    });
    return { user: user, ...(await this.newSession(user.id as string)) };
  }

  async createUser(actor: User, username: unknown, password: unknown, role: unknown): Promise<User> {
    if (actor.role !== "owner") throw new Forbidden();
    const credentials = this.checkCredentials(username, password);
    if (!this.spec.roles.some((item) => item.key === role)) throw new FieldErrors({ role: MESSAGES.invalidChoice });
    try {
      const created = await this.db
        .insertInto("_users")
        .values({ username: credentials.username, password_hash: await hash(credentials.password), role })
        .returning(["id", "username", "role"])
        .executeTakeFirstOrThrow();
      return created;
    } catch (error) {
      if ((error as { code?: string }).code === "23505") throw new FieldErrors({ username: MESSAGES.notUnique });
      throw error;
    }
  }

  async login(username: unknown, password: unknown): Promise<{ user: User; token: string; expires: Date }> {
    const name = typeof username === "string" ? username.trim() : "";
    const now = Date.now();
    const record = this.attempts.get(name);
    if (record && record.until > now && record.count >= MAX_ATTEMPTS) throw new Unauthorized(MESSAGES.throttled);
    const user = await this.db.selectFrom("_users").selectAll().where("username", "=", name).executeTakeFirst();
    const valid = await verify((user?.password_hash as string) ?? DUMMY_HASH, typeof password === "string" ? password : "").catch(() => false);
    if (!user || !valid) {
      const current = record && record.until > now ? record : { count: 0, until: now + ATTEMPT_WINDOW_MS };
      this.attempts.set(name, { count: current.count + 1, until: current.until });
      throw new Unauthorized(MESSAGES.badLogin);
    }
    this.attempts.delete(name);
    return { user: { id: user.id, username: user.username, role: user.role }, ...(await this.newSession(user.id as string)) };
  }

  async fromToken(token: string | undefined): Promise<User | null> {
    if (!token) return null;
    const row = await this.db
      .selectFrom("_sessions")
      .innerJoin("_users", "_users.id", "_sessions.user_id")
      .select(["_users.id", "_users.username", "_users.role"])
      .where("_sessions.token_hash", "=", this.tokenHash(token))
      .where("_sessions.expires_at", ">", new Date())
      .executeTakeFirst();
    return (row) ?? null;
  }

  async logout(token: string | undefined): Promise<void> {
    if (token) await this.db.deleteFrom("_sessions").where("token_hash", "=", this.tokenHash(token)).execute();
  }
}
