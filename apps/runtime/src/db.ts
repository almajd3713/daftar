/** Postgres through Kysely. Every identifier comes from a checked spec key; values are parameters. */
import { Kysely, PostgresDialect, sql, type RawBuilder, type Transaction } from "kysely";
import pg from "pg";

// Numbers come back as numbers, and dates stay plain text so no time zone can shift them.
pg.types.setTypeParser(pg.types.builtins.NUMERIC, (value) => Number.parseFloat(value));
pg.types.setTypeParser(pg.types.builtins.INT8, (value) => Number(value));
pg.types.setTypeParser(pg.types.builtins.DATE, (value) => value);
pg.types.setTypeParser(pg.types.builtins.TIMESTAMPTZ, (value) => new Date(value).toISOString());

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Db = Kysely<any>;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Tx = Transaction<any> | Kysely<any>;

const KEY = /^[a-z][a-z0-9_]{0,62}$/;
const SYSTEM = /^_[a-z][a-z0-9_]{0,61}$/;

export function createDb(connectionString: string): Db {
  return new Kysely({ dialect: new PostgresDialect({ pool: new pg.Pool({ connectionString, max: 10 }) }) });
}

/** The table for an entity key. A key that isn't a key is a bug, so it stops here, not in SQL. */
export function tableOf(key: string): string {
  if (!KEY.test(key)) throw new Error(`Not a valid key: ${JSON.stringify(key)}`);
  return `e_${key}`;
}

export function column(key: string): RawBuilder<unknown> {
  if (!KEY.test(key) && !SYSTEM.test(key)) throw new Error(`Not a valid key: ${JSON.stringify(key)}`);
  return sql.ref(key);
}
