/** C-10 config keys the runtime reads. It refuses to start without a secret. */
export interface Config {
  databaseUrl: string;
  specPath: string;
  secret: string;
  defaultLocale: "fr-DZ" | "ar-DZ";
  timezone: string;
  workerUrl: string | undefined;
  processor: string | undefined;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const missing = ["DAFTAR_DATABASE_URL", "DAFTAR_SPEC_PATH", "DAFTAR_SECRET"].filter((key) => !env[key]);
  if (missing.length) throw new Error(`Missing configuration: ${missing.join(", ")}`);
  const locale = env.DAFTAR_DEFAULT_LOCALE ?? "fr-DZ";
  if (locale !== "fr-DZ" && locale !== "ar-DZ") throw new Error("DAFTAR_DEFAULT_LOCALE must be fr-DZ or ar-DZ");
  return {
    databaseUrl: env.DAFTAR_DATABASE_URL as string,
    specPath: env.DAFTAR_SPEC_PATH as string,
    secret: env.DAFTAR_SECRET as string,
    defaultLocale: locale,
    timezone: env.DAFTAR_TZ ?? "Africa/Algiers",
    workerUrl: env.DAFTAR_WORKER_URL,
    processor: env.DAFTAR_PROCESSOR_NAME,
  };
}
