/** `node dist/preview.js`, started by the Studio. It ends when told to, or when the Studio goes away. */
import { startPreview } from "./preview-server.js";

const { DAFTAR_PREVIEW_ADMIN_URL: adminUrl, DAFTAR_PREVIEW_DATABASE: databaseName, DAFTAR_SPEC_PATH: specPath } = process.env;
if (!adminUrl || !databaseName || !specPath) throw new Error("Missing preview configuration");

const preview = await startPreview({ adminUrl, databaseName, specPath });
let stopping = false;
const finish = (): void => {
  if (stopping) return;
  stopping = true;
  void preview.stop().finally(() => process.exit(0));
};
process.on("SIGTERM", finish);
process.on("SIGINT", finish);
process.stdin.on("end", finish);
process.stdin.resume();
console.log(JSON.stringify({ port: preview.port, cookie: preview.cookie }));
