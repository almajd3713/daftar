import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { Client, PASSWORD, example, ownerOf, start, userOf, type Running } from "./helpers.js";

const FIXED = new Date("2026-03-10T10:00:00Z");

describe.each(["tutoring-register", "payments-ledger", "fee-calculator", "repair-tracker"])("%s boots", (name) => {
  it("migrates, serves meta, and boots again on the same database", async () => {
    const running = await start(example(name));
    try {
      const owner = await ownerOf(running);
      const meta = await owner.get("/api/meta");
      expect(meta.status).toBe(200);
      expect(meta.body.specVersion).toBe("1.0.0");
      expect(meta.body.user.role).toBe("owner");
    } finally {
      await running.close();
    }
  });
});

describe("auth", () => {
  let running: Running;
  beforeAll(async () => {
    running = await start(example("repair-tracker"));
  });
  afterAll(() => running.close());

  it("has no default credentials and needs setup", async () => {
    const anyone = new Client(running.base);
    expect((await anyone.get("/api/auth/status")).body).toEqual({ needsSetup: true });
    expect((await anyone.get("/api/meta")).status).toBe(401);
    expect((await anyone.get("/api/e/repairs")).status).toBe(401);
    expect((await anyone.post("/api/auth/login", { username: "admin", password: "admin" })).status).toBe(401);
  });

  it("refuses a weak password, then makes the first account the owner, once", async () => {
    const first = new Client(running.base);
    const weak = await first.post("/api/auth/setup", { username: "o", password: "court" });
    expect(weak.status).toBe(400);
    expect(weak.body.fields.password.ar).toBeTruthy();
    expect((await first.post("/api/auth/setup", { username: "o", password: PASSWORD })).status).toBe(201);
    expect((await first.get("/api/auth/me")).body).toEqual({ username: "o", role: "owner" });
    const second = await new Client(running.base).post("/api/auth/setup", { username: "x", password: PASSWORD });
    expect(second.status).toBe(409);
    expect((await new Client(running.base).get("/api/auth/status")).body).toEqual({ needsSetup: false });
  });

  it("sets an HttpOnly, SameSite session cookie, and logout ends it", async () => {
    const response = await fetch(`${running.base}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "o", password: PASSWORD }),
    });
    const cookie = response.headers.get("set-cookie") ?? "";
    expect(cookie).toMatch(/HttpOnly/i);
    expect(cookie).toMatch(/SameSite=Lax/i);
    const client = new Client(running.base);
    await client.post("/api/auth/login", { username: "o", password: PASSWORD });
    expect((await client.get("/api/auth/me")).status).toBe(200);
    expect((await client.post("/api/auth/logout")).status).toBe(204);
    expect((await client.get("/api/auth/me")).status).toBe(401);
  });

  it("slows down password guessing", async () => {
    const client = new Client(running.base);
    for (let i = 0; i < 5; i += 1) expect((await client.post("/api/auth/login", { username: "cible", password: "faux-mot-de-passe" })).status).toBe(401);
    const response = await client.post("/api/auth/login", { username: "cible", password: "faux-mot-de-passe" });
    expect(response.body.reason.fr).toContain("Trop d'essais");
  });

  it("only lets the owner create accounts", async () => {
    const owner = new Client(running.base);
    await owner.post("/api/auth/login", { username: "o", password: PASSWORD });
    const staff = await userOf(running, owner, "staff", "s1");
    expect((await staff.post("/api/auth/users", { username: "x", password: PASSWORD, role: "owner" })).status).toBe(403);
    expect((await owner.post("/api/auth/users", { username: "y", password: PASSWORD, role: "admin" })).status).toBe(400);
  });

  it("refuses a write that isn't JSON, which a cross-site form would be", async () => {
    const response = await fetch(`${running.base}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "username=o&password=x",
    });
    expect(response.status).toBe(415);
  });
});

describe("roles (R-17)", () => {
  let running: Running;
  let owner: Client;
  let staff: Client;
  let accountant: Client;
  let viewer: Client;
  let otherStaff: Client;
  let paymentId: string;

  const payment = { receipt_no: "R1", payer: "Sara", period: "2026-01-01", due_on: "2026-02-01", amount_due: 1000, amount_paid: 400, cost: 300, status: "partial" };

  beforeAll(async () => {
    running = await start(example("payments-ledger"), () => FIXED);
    owner = await ownerOf(running);
    staff = await userOf(running, owner, "staff");
    otherStaff = await userOf(running, owner, "staff", "staff2");
    accountant = await userOf(running, owner, "accountant");
    viewer = await userOf(running, owner, "viewer");
    const created = await owner.post("/api/e/payments", payment);
    expect(created.status).toBe(201);
    paymentId = created.body._id;
  });
  afterAll(() => running.close());

  it("owner sees everything and can change anything", async () => {
    const row = (await owner.get(`/api/e/payments/${paymentId}`)).body;
    expect(row.cost).toBe(300);
    expect(row.margin).toBe(100); // MROUND(400-300,10), through the engine.
    expect((await owner.patch(`/api/e/payments/${paymentId}`, { payer: "Sara H." })).status).toBe(200);
  });

  it("staff can create and edit, but not delete, export or see sensitive fields", async () => {
    const created = await staff.post("/api/e/payments", { ...payment, receipt_no: "R2", cost: undefined });
    expect(created.status).toBe(201);
    expect(created.body).not.toHaveProperty("cost");
    expect(created.body).not.toHaveProperty("margin");
    expect(created.body.remaining).toBe(600);
    expect((await staff.del(`/api/e/payments/${created.body._id}`)).status).toBe(403);
  });

  it("staff can't write a sensitive field, as if it didn't exist", async () => {
    const response = await staff.post("/api/e/payments", { ...payment, receipt_no: "R3" });
    expect(response.status).toBe(400);
    expect(response.body.fields.cost.fr).toContain("n'existe pas");
  });

  it("a staff member sees only their own records here", async () => {
    const mine = await staff.get("/api/e/payments");
    expect(mine.body.rows.map((row: any) => row.receipt_no)).toEqual(["R2"]);
    expect((await otherStaff.get("/api/e/payments")).body.rows).toEqual([]);
    expect((await staff.get(`/api/e/payments/${paymentId}`)).status).toBe(404);
    expect((await staff.patch(`/api/e/payments/${paymentId}`, { payer: "x" })).status).toBe(404);
    expect((await staff.get(`/api/e/payments/${paymentId}/history`)).status).toBe(404);
  });

  it("accountant reads everything including sensitive fields, and can't write", async () => {
    const row = (await accountant.get(`/api/e/payments/${paymentId}`)).body;
    expect(row.cost).toBe(300);
    expect((await accountant.patch(`/api/e/payments/${paymentId}`, { payer: "x" })).status).toBe(403);
    expect((await accountant.post("/api/e/payments", payment)).status).toBe(403);
  });

  it("viewer reads, without sensitive fields, and can't write", async () => {
    const row = (await viewer.get(`/api/e/payments/${paymentId}`)).body;
    expect(row.payer).toBe("Sara H.");
    expect(row).not.toHaveProperty("cost");
    expect(row).not.toHaveProperty("margin");
    expect((await viewer.patch(`/api/e/payments/${paymentId}`, { payer: "x" })).status).toBe(403);
  });

  it("a hidden field can't be sorted, filtered or totalled, which would reveal it", async () => {
    expect((await viewer.get("/api/e/payments?sort=cost")).status).toBe(400);
    expect((await viewer.get("/api/e/payments?filter.cost.gt=100")).status).toBe(400);
    expect((await viewer.get("/api/e/payments?totals=cost")).status).toBe(400);
    expect((await accountant.get("/api/e/payments?totals=cost")).body.totals.cost).toBeGreaterThan(0);
  });

  it("history masks sensitive changes for those who can't see them", async () => {
    await owner.patch(`/api/e/payments/${paymentId}`, { cost: 350 });
    const forViewer = (await viewer.get(`/api/e/payments/${paymentId}/history`)).body.changes;
    expect(JSON.stringify(forViewer)).not.toContain("350");
    expect(forViewer[0].changes.cost).toEqual(["*", "*"]);
    const forOwner = (await owner.get(`/api/e/payments/${paymentId}/history`)).body.changes;
    expect(forOwner[0].changes.cost).toEqual([300, 350]);
  });

  it("the audit export masks too, and only some roles get it", async () => {
    expect((await staff.get("/api/audit.csv")).status).toBe(403);
    expect((await viewer.get("/api/audit.csv")).status).toBe(403);
    const forAccountant = await accountant.get("/api/audit.csv");
    expect(forAccountant.status).toBe(200);
    expect(forAccountant.text).toContain("350");
  });

  it("meta hides sensitive fields from every part of the spec", async () => {
    const meta = (await viewer.get("/api/meta")).body;
    const text = JSON.stringify(meta);
    expect(text).not.toContain('"cost"');
    expect(text).not.toContain('"margin"');
    expect(text).not.toContain("provenance");
    expect(text).not.toContain("MROUND");
    expect(meta.forms).toEqual([]);
    expect(JSON.stringify((await owner.get("/api/meta")).body)).toContain('"cost"');
  });

  it("a stale write is refused", async () => {
    const row = (await owner.get(`/api/e/payments/${paymentId}`)).body;
    expect((await owner.patch(`/api/e/payments/${paymentId}`, { payer: "A", _version: row._version })).status).toBe(200);
    const stale = await owner.patch(`/api/e/payments/${paymentId}`, { payer: "B", _version: row._version });
    expect(stale.status).toBe(409);
    expect(stale.body.reason.ar).toBeTruthy();
  });
});

describe("the record API", () => {
  let running: Running;
  let owner: Client;

  beforeAll(async () => {
    running = await start(example("tutoring-register"));
    owner = await ownerOf(running);
  });
  afterAll(() => running.close());

  async function classId(code: string): Promise<string> {
    return (await owner.post("/api/e/classes", { code, name: `Classe ${code}`, monthly_fee: 3000 })).body._id;
  }

  it("validates, with messages in both languages, and accepts Algerian formats", async () => {
    const klass = await classId("C1");
    const response = await owner.post("/api/e/students", { full_name: "", parent_phone: "123", level: "ghost", class: "not-a-uuid", birth_date: "2026-13-45", nope: 1 });
    expect(response.status).toBe(400);
    expect(Object.keys(response.body.fields).sort()).toEqual(["birth_date", "class", "full_name", "level", "nope", "parent_phone"]);
    expect(response.body.fields.parent_phone.fr).toContain("algérien");
    expect(response.body.fields.parent_phone.ar).toMatch(/[؀-ۿ]/);
    const good = await owner.post("/api/e/students", { full_name: "أمينة", parent_phone: "٠٥٥٠ ١٢ ٣٤ ٥٦", level: "cem", class: klass });
    expect(good.status).toBe(201);
    expect(good.body.parent_phone).toBe("0550123456");
    expect(good.body._name).toBe("EL-0001");
  });

  it("refuses a link to nothing, and a duplicate where it must be unique", async () => {
    const missing = await owner.post("/api/e/students", { full_name: "x", parent_phone: "0550123456", level: "cem", class: "00000000-0000-4000-8000-000000000000" });
    expect(missing.body.fields.class).toBeTruthy();
    await classId("DUP");
    const duplicate = await owner.post("/api/e/classes", { code: "DUP", name: "Autre" });
    expect(duplicate.status).toBe(400);
    expect(duplicate.body.fields.code.fr).toContain("existe déjà");
  });

  it("restricts deleting what others depend on", async () => {
    const klass = await classId("LINK");
    await owner.post("/api/e/students", { full_name: "y", parent_phone: "0661234567", level: "cem", class: klass });
    const response = await owner.del(`/api/e/classes/${klass}`);
    expect(response.status).toBe(409);
    expect(response.body.reason.fr).toContain("dépendent");
  });

  it("lists with filter, sort, search, paging and totals", async () => {
    for (const [code, fee] of [["A", 1000], ["B", 2000], ["C", 3000]] as const) await owner.post("/api/e/classes", { code: `L${code}`, name: `Liste ${code}`, monthly_fee: fee });
    const sorted = await owner.get("/api/e/classes?filter.name.contains=Liste&sort=-monthly_fee&totals=monthly_fee&pageSize=2");
    expect(sorted.body.rows.map((row: any) => row.code)).toEqual(["LC", "LB"]);
    expect(sorted.body.total).toBe(3);
    expect(sorted.body.totals.monthly_fee).toBe(6000);
    const second = await owner.get("/api/e/classes?filter.name.contains=Liste&sort=-monthly_fee&pageSize=2&page=2");
    expect(second.body.rows.map((row: any) => row.code)).toEqual(["LA"]);
    expect((await owner.get("/api/e/classes?filter.monthly_fee.ge=2000&filter.name.contains=Liste")).body.total).toBe(2);
    expect((await owner.get("/api/e/classes?filter.code.in=LA,LB")).body.total).toBe(2);
    const students = await owner.get("/api/e/students?q=أمينة");
    expect(students.body.total).toBe(1);
  });

  it("treats hostile input as data, never as SQL", async () => {
    const payload = `x'; DROP TABLE e_classes; --`;
    expect((await owner.post("/api/e/classes", { code: payload, name: payload })).status).toBe(201);
    expect((await owner.get(`/api/e/classes?q=${encodeURIComponent(payload)}`)).body.total).toBe(1);
    expect((await owner.get(`/api/e/classes?sort=${encodeURIComponent('name; DROP TABLE e_classes')}`)).status).toBe(400);
    expect((await owner.get(`/api/e/classes?filter.${encodeURIComponent('name" OR 1=1')}=x`)).status).toBe(200);
    expect((await owner.get("/api/e/e_classes")).status).toBe(404);
    expect((await owner.get("/api/e/classes?filter.name.contains=%25")).body.total).toBeLessThan(20);
    expect((await owner.get("/api/e/classes")).status).toBe(200);
  });

  it("gives 404 for an unknown entity or a malformed id", async () => {
    expect((await owner.get("/api/e/ghost")).status).toBe(404);
    expect((await owner.get("/api/e/classes/not-a-uuid")).status).toBe(404);
    expect((await owner.get("/api/e/classes/00000000-0000-4000-8000-000000000000")).status).toBe(404);
  });

  it("exports a processing register from the spec (R-24)", async () => {
    const register = (await owner.get("/api/register")).body;
    expect(register.processor).toBe("Atelier de test");
    expect(register.personalData.map((item: any) => item.entity)).toEqual(["students"]);
    expect(register.personalData[0].retention.months).toBe(36);
    const fields = register.personalData[0].fields.map((item: any) => item.key);
    expect(fields).toEqual(["full_name", "birth_date", "parent_name", "parent_phone"]);
    expect(register.personalData[0].accessBy.map((item: any) => item.role)).toEqual(["owner", "staff", "accountant", "viewer"]);
    const viewer = await userOf(running, owner, "viewer", "v2");
    expect((await viewer.get("/api/register")).status).toBe(403);
  });
});

describe("history, revert and batch undo (R-18)", () => {
  let running: Running;
  let owner: Client;
  let staff: Client;

  beforeAll(async () => {
    running = await start(example("tutoring-register"));
    owner = await ownerOf(running);
    staff = await userOf(running, owner, "staff");
  });
  afterAll(() => running.close());

  const klass = (code: string, fee = 1000) => owner.post("/api/e/classes", { code, name: `N ${code}`, monthly_fee: fee });

  it("records who, when, source and per-field values for each write", async () => {
    const created = await klass("H1", 1000);
    const id = created.body._id;
    await owner.patch(`/api/e/classes/${id}`, { monthly_fee: 2000, name: "Nouveau" });
    await owner.patch(`/api/e/classes/${id}`, { monthly_fee: 2000 }); // Nothing changed: nothing recorded.
    const { changes } = (await owner.get(`/api/e/classes/${id}/history`)).body;
    expect(changes.map((change: any) => change.op)).toEqual(["update", "create"]);
    expect(changes[0]).toMatchObject({ actor: "owner", source: "ui", entity: "classes", recordId: id });
    expect(changes[0].at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(changes[0].changes).toEqual({ monthly_fee: [1000, 2000], name: ["N H1", "Nouveau"] });
    expect(changes[1].changes.code).toEqual([null, "H1"]);
  });

  it("reverts one change, recorded as its own entry", async () => {
    const { _id: id } = (await klass("R1", 1000)).body;
    await owner.patch(`/api/e/classes/${id}`, { monthly_fee: 2000 });
    const [change] = (await owner.get(`/api/e/classes/${id}/history`)).body.changes;
    expect((await owner.post(`/api/changes/${change.id}/revert`)).status).toBe(204);
    expect((await owner.get(`/api/e/classes/${id}`)).body.monthly_fee).toBe(1000);
    const { changes } = (await owner.get(`/api/e/classes/${id}/history`)).body;
    expect(changes[0]).toMatchObject({ op: "revert", revertOf: change.id });
    expect(changes[0].changes.monthly_fee).toEqual([2000, 1000]);
    expect((await owner.post(`/api/changes/${change.id}/revert`)).status).toBe(409);
  });

  it("refuses a revert that would overwrite a later edit", async () => {
    const { _id: id } = (await klass("R2", 1000)).body;
    await owner.patch(`/api/e/classes/${id}`, { monthly_fee: 2000 });
    const [change] = (await owner.get(`/api/e/classes/${id}/history`)).body.changes;
    await owner.patch(`/api/e/classes/${id}`, { monthly_fee: 3000 });
    const response = await owner.post(`/api/changes/${change.id}/revert`);
    expect(response.status).toBe(409);
    expect(response.body.reason.fr).toContain("ont changé");
    expect((await owner.get(`/api/e/classes/${id}`)).body.monthly_fee).toBe(3000);
  });

  it("reverts a delete, bringing the record back as it was, and reverts a create", async () => {
    const { _id: id, _name: name } = (await klass("R3", 1000)).body;
    await owner.del(`/api/e/classes/${id}`);
    expect((await owner.get(`/api/e/classes/${id}`)).status).toBe(404);
    const [deletion] = (await owner.get(`/api/e/classes/${id}/history`)).body.changes;
    expect(deletion.op).toBe("delete");
    expect((await owner.post(`/api/changes/${deletion.id}/revert`)).status).toBe(204);
    const back = (await owner.get(`/api/e/classes/${id}`)).body;
    expect(back).toMatchObject({ code: "R3", monthly_fee: 1000, _name: name });
    const creation = (await owner.get(`/api/e/classes/${id}/history`)).body.changes.at(-1);
    expect(creation.op).toBe("create");
    expect((await owner.post(`/api/changes/${creation.id}/revert`)).status).toBe(204);
    expect((await owner.get(`/api/e/classes/${id}`)).status).toBe(404);
  });

  it("only those with the revert right may revert", async () => {
    const { _id: id } = (await klass("R4", 1000)).body;
    const [change] = (await owner.get(`/api/e/classes/${id}/history`)).body.changes;
    expect((await staff.post(`/api/changes/${change.id}/revert`)).status).toBe(403);
  });

  it("undoes a whole import batch at once, and only once", async () => {
    const { RecordService } = await import("../src/records/service.js");
    const service = new RecordService(running.db, example("tutoring-register"));
    const { batchId, created } = await service.createBatch("classes", [
      { code: "B1", name: "Un", monthly_fee: 1 },
      { code: "B2", name: "Deux", monthly_fee: 2 },
      { code: "B3", name: "Trois", monthly_fee: 3 },
    ]);
    expect(created).toBe(3);
    const listed = await owner.get("/api/e/classes?filter.code.in=B1,B2,B3");
    expect(listed.body.total).toBe(3);
    const history = (await owner.get(`/api/e/classes/${listed.body.rows[0]._id}/history`)).body.changes[0];
    expect(history).toMatchObject({ source: "import", batchId, actor: "system" });
    expect((await staff.post(`/api/batches/${batchId}/undo`)).status).toBe(403);
    const undo = await owner.post(`/api/batches/${batchId}/undo`);
    expect(undo.status).toBe(200);
    expect(undo.body.undone).toBe(3);
    expect((await owner.get("/api/e/classes?filter.code.in=B1,B2,B3")).body.total).toBe(0);
    expect((await owner.post(`/api/batches/${batchId}/undo`)).status).toBe(409);
  });

  it("refuses to undo a batch partly: one later edit keeps all of it", async () => {
    const records = (await import("../src/records/service.js")).RecordService;
    const service = new records(running.db, example("tutoring-register"));
    const { batchId } = await service.createBatch("classes", [
      { code: "P1", name: "Un", monthly_fee: 1 },
      { code: "P2", name: "Deux", monthly_fee: 2 },
    ]);
    const rows = (await owner.get("/api/e/classes?filter.code=P2")).body.rows;
    await owner.patch(`/api/e/classes/${rows[0]._id}`, { monthly_fee: 99 });
    expect((await owner.post(`/api/batches/${batchId}/undo`)).status).toBe(409);
    expect((await owner.get("/api/e/classes?filter.code.in=P1,P2")).body.total).toBe(2);
  });
});

describe("computed fields (R-19)", () => {
  let running: Running;
  let owner: Client;

  beforeAll(async () => {
    running = await start(example("payments-ledger"), () => FIXED);
    owner = await ownerOf(running);
  });
  afterAll(() => running.close());

  const base = { payer: "Sara", period: "2026-01-01", status: "unpaid" };

  it("recompute on every write, translated and through the engine", async () => {
    const created = (await owner.post("/api/e/payments", { ...base, receipt_no: "C1", amount_due: 1000.5, amount_paid: 400.25, cost: 123 })).body;
    expect(created.remaining).toBeCloseTo(600.25, 9);
    expect(created.margin).toBe(280); // MROUND(400.25-123,10).
    const updated = (await owner.patch(`/api/e/payments/${created._id}`, { amount_paid: 1000.5, cost: 100 })).body;
    expect(updated.remaining).toBe(0);
    expect(updated.margin).toBe(900);
  });

  it("aren't writable, and aren't recorded in history", async () => {
    const created = (await owner.post("/api/e/payments", { ...base, receipt_no: "C2", amount_due: 10, amount_paid: 1 })).body;
    const refused = await owner.patch(`/api/e/payments/${created._id}`, { remaining: 5 });
    expect(refused.status).toBe(400);
    expect(refused.body.fields.remaining.fr).toContain("calculé");
    await owner.patch(`/api/e/payments/${created._id}`, { amount_paid: 2 });
    const { changes } = (await owner.get(`/api/e/payments/${created._id}/history`)).body;
    expect(Object.keys(changes[0].changes)).toEqual(["amount_paid"]);
    expect(Object.keys(changes[1].changes)).not.toContain("remaining");
    expect(Object.keys(changes[1].changes)).not.toContain("margin");
  });

  it("a revert recomputes too", async () => {
    const created = (await owner.post("/api/e/payments", { ...base, receipt_no: "C3", amount_due: 100, amount_paid: 10 })).body;
    await owner.patch(`/api/e/payments/${created._id}`, { amount_paid: 60 });
    const [change] = (await owner.get(`/api/e/payments/${created._id}/history`)).body.changes;
    await owner.post(`/api/changes/${change.id}/revert`);
    expect((await owner.get(`/api/e/payments/${created._id}`)).body.remaining).toBe(90);
  });

  it("match Excel within R-19's tolerance on values Excel would compute", async () => {
    const created = (await owner.post("/api/e/payments", { ...base, receipt_no: "C4", amount_due: 0.3, amount_paid: 0.1 })).body;
    const excel = 0.2;
    expect(Math.abs(created.remaining - excel)).toBeLessThanOrEqual(1e-9 * excel);
  });
});

describe("workflow and reminders (R-20)", () => {
  let running: Running;
  let owner: Client;
  let staff: Client;
  let viewer: Client;
  const today = new Date("2026-03-10T10:00:00Z");

  beforeAll(async () => {
    running = await start(example("repair-tracker"), () => today);
    owner = await ownerOf(running);
    staff = await userOf(running, owner, "staff");
    viewer = await userOf(running, owner, "viewer");
  });
  afterAll(() => running.close());

  const repair = (extra: object = {}) => staff.post("/api/e/repairs", { device: "Téléphone", customer: "Sara", received_on: "2026-03-01", ...extra });

  it("a new record starts in the initial state, and the state can't be edited directly", async () => {
    const created = await repair();
    expect(created.body.status).toBe("received");
    const direct = await staff.patch(`/api/e/repairs/${created.body._id}`, { status: "delivered" });
    expect(direct.status).toBe(400);
    expect(direct.body.fields.status.fr).toContain("actions");
    const forced = await repair({ status: "delivered" });
    expect(forced.status).toBe(400);
  });

  it("allows only the transitions the spec defines, and says why it refuses", async () => {
    const { _id: id } = (await repair({ price: 500 })).body;
    const early = await staff.post(`/api/e/repairs/${id}/transition`, { action: "deliver" });
    expect(early.status).toBe(409);
    expect(early.body.reason.fr).toContain("état actuel");
    expect(early.body.reason.ar).toMatch(/[؀-ۿ]/);
    const moved = await staff.post(`/api/e/repairs/${id}/transition`, { action: "start_repair" });
    expect(moved.status).toBe(200);
    expect(moved.body.status).toBe("in_repair");
    const { changes } = (await staff.get(`/api/e/repairs/${id}/history`)).body;
    expect(changes[0]).toMatchObject({ op: "transition", source: "workflow" });
    expect(changes[0].changes.status).toEqual(["received", "in_repair"]);
    expect((await staff.post(`/api/e/repairs/${id}/transition`, { action: "ghost" })).status).toBe(404);
  });

  it("checks a transition's condition", async () => {
    const { _id: id } = (await repair()).body;
    await staff.post(`/api/e/repairs/${id}/transition`, { action: "start_repair" });
    const refused = await staff.post(`/api/e/repairs/${id}/transition`, { action: "mark_ready" });
    expect(refused.status).toBe(409);
    expect(refused.body.reason.fr).toContain("conditions");
    await staff.patch(`/api/e/repairs/${id}`, { price: 500 });
    expect((await staff.post(`/api/e/repairs/${id}/transition`, { action: "mark_ready" })).body.status).toBe("ready");
  });

  it("refuses a role that can't update at all", async () => {
    const { _id: id } = (await repair()).body;
    expect((await viewer.post(`/api/e/repairs/${id}/transition`, { action: "start_repair" })).status).toBe(403);
  });

  it("computes the masked margin only for those who may see it", async () => {
    const created = (await owner.post("/api/e/repairs", { device: "PC", customer: "Omar", received_on: "2026-03-02", price: 500, parts_cost: 120 })).body;
    expect(created.margin).toBe(380);
    expect((await staff.get(`/api/e/repairs/${created._id}`)).body).not.toHaveProperty("margin");
  });

  it("reminders appear on the right day, for the right roles, respecting filters", async () => {
    // The rule fires 1 day before promised_on, for received and in_repair records.
    const due = (await repair({ device: "Dû demain", promised_on: "2026-03-11" })).body;
    await repair({ device: "Plus tard", promised_on: "2026-03-20" });
    const delivered = (await owner.post("/api/e/repairs", { device: "Déjà prêt", customer: "x", received_on: "2026-03-01", promised_on: "2026-03-11", price: 10 })).body;
    await owner.post(`/api/e/repairs/${delivered._id}/transition`, { action: "start_repair" });
    await owner.post(`/api/e/repairs/${delivered._id}/transition`, { action: "mark_ready" });
    const { notifications } = (await staff.get("/api/notifications")).body;
    expect(notifications.map((item: any) => item.recordId)).toEqual([due._id]);
    expect(notifications[0].message.ar).toMatch(/[؀-ۿ]/);
    expect((await viewer.get("/api/notifications")).body.notifications).toEqual([]);
  });
});

describe("calculators", () => {
  let running: Running;
  let owner: Client;

  beforeAll(async () => {
    running = await start(example("fee-calculator"));
    owner = await ownerOf(running);
  });
  afterAll(() => running.close());

  it("reproduces every test case stored in the spec", async () => {
    for (const testCase of example("fee-calculator").calculators[0]!.testCases) {
      const result = await owner.post("/api/calc/tuition_fee", testCase.inputs);
      expect(result.status).toBe(200);
      for (const [key, value] of Object.entries(testCase.outputs)) expect(result.body.outputs[key]).toBeCloseTo(value as number, 9);
    }
  });

  it("uses defaults for inputs not given, and refuses bad ones", async () => {
    expect((await owner.post("/api/calc/tuition_fee", {})).body.outputs.total).toBe(3000);
    expect((await owner.post("/api/calc/tuition_fee", { subjects: "beaucoup" })).status).toBe(400);
    expect((await owner.post("/api/calc/ghost", {})).status).toBe(404);
  });

  it("needs a signed-in user", async () => {
    expect((await new Client(running.base).post("/api/calc/tuition_fee", {})).status).toBe(401);
  });

  it("doesn't reveal the model through meta", async () => {
    expect(JSON.stringify((await owner.get("/api/meta")).body)).not.toContain("=IF(");
  });
});

describe("migrations", () => {
  it("applies additive changes on boot, and stops before a destructive one", async () => {
    const { newDatabase } = await import("./helpers.js");
    const { createApp } = await import("../src/app.js");
    const { applyMigration, MigrationBlocked, planMigration, isDestructive } = await import("../src/schema/migrate.js");
    const { db, drop } = await newDatabase();
    const config = { secret: "s", timezone: "Africa/Algiers", processor: undefined };
    try {
      const spec = structuredClone(example("repair-tracker"));
      await (await createApp({ spec, db, config })).close().catch(() => undefined);

      const added = structuredClone(spec);
      added.entities[0]!.fields.push({ key: "note", label: { fr: "Note", ar: "ملاحظة" }, type: "text" });
      const additive = await planMigration(db, added);
      expect(additive.addColumns.map((item) => item.column)).toEqual(["note"]);
      expect(isDestructive(additive)).toBe(false);
      await applyMigration(db, additive);

      const removed = structuredClone(added) as any;
      removed.entities[0].fields = removed.entities[0].fields.filter((field: { key: string }) => field.key !== "problem");
      removed.forms[0].sections[1].fields = removed.forms[0].sections[1].fields.filter((key: string) => key !== "problem");
      removed.mapping[0].columns = removed.mapping[0].columns.filter((item: { field: string }) => item.field !== "problem");
      const destructive = await planMigration(db, removed);
      expect(destructive.dropColumns).toEqual([{ table: "e_repairs", column: "problem" }]);
      await expect(applyMigration(db, destructive)).rejects.toThrow(MigrationBlocked);
      await expect(applyMigration(db, destructive, { confirmDestructive: true })).rejects.toThrow(MigrationBlocked);
      await expect(createApp({ spec: removed, db, config })).rejects.toThrow(MigrationBlocked);
      await applyMigration(db, destructive, { confirmDestructive: true, backupReference: "/backups/dump.sql" });
      expect((await planMigration(db, removed)).dropColumns).toEqual([]);
    } finally {
      await drop();
    }
  });

  it("will not build SQL from a key that isn't a key", async () => {
    const { tableOf, column } = await import("../src/db.js");
    expect(() => tableOf('x"; DROP TABLE y; --')).toThrow(/valid key/);
    expect(() => column("a b")).toThrow(/valid key/);
    expect(tableOf("students")).toBe("e_students");
  });
});

describe("computed fields across records", () => {
  function linked(): any {
    const spec = structuredClone(example("tutoring-register")) as any;
    const [classes, students] = spec.entities;
    students.fields.push({
      key: "fee", label: { fr: "Frais", ar: "رسوم" }, type: "computed", resultType: "money",
      computed: { eval: "translated", excel: "=VLOOKUP(F2,Classes!A:C,3,FALSE)", deps: ["class.monthly_fee"], store: true,
        expr: { kind: "related", valueType: "number", via: "class", field: "monthly_fee" } },
    });
    classes.fields.push({
      key: "headcount", label: { fr: "Effectif", ar: "العدد" }, type: "computed", resultType: "integer",
      computed: { eval: "translated", excel: "=COUNTIF(Eleves!F:F,A2)", deps: ["students"], store: true,
        expr: { kind: "rollup", valueType: "number", via: "students", fn: "count" } },
    });
    return spec;
  }

  it("follow a link, and update when what they read changes", async () => {
    const running = await start(linked());
    try {
      const owner = await ownerOf(running);
      const klass = (await owner.post("/api/e/classes", { code: "A", name: "A", monthly_fee: 3000 })).body;
      const student = (await owner.post("/api/e/students", { full_name: "x", parent_phone: "0550123456", level: "cem", class: klass._id })).body;
      expect(student.fee).toBe(3000);
      await owner.patch(`/api/e/classes/${klass._id}`, { monthly_fee: 3500 });
      expect((await owner.get(`/api/e/students/${student._id}`)).body.fee).toBe(3500);
    } finally {
      await running.close();
    }
  });

  it("roll up over children, and update when a child comes or goes", async () => {
    const running = await start(linked());
    try {
      const owner = await ownerOf(running);
      const klass = (await owner.post("/api/e/classes", { code: "A", name: "A" })).body;
      expect(klass.headcount).toBe(0);
      const one = (await owner.post("/api/e/students", { full_name: "x", parent_phone: "0550123456", level: "cem", class: klass._id })).body;
      await owner.post("/api/e/students", { full_name: "y", parent_phone: "0550123457", level: "cem", class: klass._id });
      expect((await owner.get(`/api/e/classes/${klass._id}`)).body.headcount).toBe(2);
      await owner.del(`/api/e/students/${one._id}`);
      expect((await owner.get(`/api/e/classes/${klass._id}`)).body.headcount).toBe(1);
    } finally {
      await running.close();
    }
  });
});

describe("errors are never hidden as values (R-19)", () => {
  function withFormula(computed: object): any {
    const spec = structuredClone(example("payments-ledger")) as any;
    const margin = spec.entities[0].fields.find((field: { key: string }) => field.key === "margin");
    margin.computed = computed;
    return spec;
  }
  const row = { receipt_no: "E1", payer: "x", period: "2026-01-01", amount_due: 10, amount_paid: 0, status: "unpaid" };

  it("an Excel error shows as an error, not as zero or blank", async () => {
    const running = await start(withFormula({ eval: "engine", excel: "=D3/E3", deps: ["amount_due", "amount_paid"], store: true }));
    try {
      const owner = await ownerOf(running);
      const created = (await owner.post("/api/e/payments", row)).body;
      expect(created.margin).toBeNull();
      expect(created._errors.margin).toBe("#DIV/0!");
      const fixed = (await owner.patch(`/api/e/payments/${created._id}`, { amount_paid: 5 })).body;
      expect(fixed.margin).toBe(2);
      expect(fixed._errors).toBeUndefined();
    } finally {
      await running.close();
    }
  });

  it("a function the engine doesn't know reports #NAME?", async () => {
    const running = await start(withFormula({ eval: "engine", excel: "=MACROFONCTION(D3)", deps: ["amount_due"], store: true }));
    try {
      const owner = await ownerOf(running);
      expect((await owner.post("/api/e/payments", row)).body._errors.margin).toBe("#NAME?");
    } finally {
      await running.close();
    }
  });

  it("an engine formula with no layout to run on says so", async () => {
    const spec = withFormula({ eval: "engine", excel: "=D3*2", deps: ["amount_due"], store: true });
    spec.mapping = [];
    const running = await start(spec);
    try {
      const owner = await ownerOf(running);
      const created = (await owner.post("/api/e/payments", row)).body;
      expect(created.margin).toBeNull();
      expect(created._errors.margin).toBe("#ENGINE!");
    } finally {
      await running.close();
    }
  });

  it("a sensitive field's error is hidden with the field", async () => {
    const running = await start(withFormula({ eval: "engine", excel: "=D3/E3", deps: ["amount_due", "amount_paid"], store: true }));
    try {
      const owner = await ownerOf(running);
      const viewer = await userOf(running, owner, "viewer");
      const created = (await owner.post("/api/e/payments", row)).body;
      expect((await viewer.get(`/api/e/payments/${created._id}`)).body._errors).toBeUndefined();
    } finally {
      await running.close();
    }
  });
});
