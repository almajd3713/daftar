/** Who may see and do what, all generated from the spec's roles (R-17). */
import type { DaftarSpec, Entity, Field, Permission, Role } from "@daftar/spec/types";

export interface User {
  id: string;
  username: string;
  role: string;
}

/** Internal work: seed loads, and undoing a batch. It isn't a login and never comes from a request. */
export const SYSTEM_USER: User = { id: "00000000-0000-0000-0000-000000000000", username: "system", role: "system" };

export type Action = "read" | "create" | "update" | "delete" | "export" | "import" | "revert";

export function roleOf(spec: DaftarSpec, user: User): Role | undefined {
  return spec.roles.find((role) => role.key === user.role);
}

export function permissionOf(spec: DaftarSpec, user: User, entity: string): Permission | undefined {
  return roleOf(spec, user)?.permissions.find((item) => item.entity === entity);
}

export function can(spec: DaftarSpec, user: User, entity: string, action: Action): boolean {
  if (user === SYSTEM_USER) return true;
  return permissionOf(spec, user, entity)?.actions.includes(action) ?? false;
}

export function ownOnly(spec: DaftarSpec, user: User, entity: string): boolean {
  if (user === SYSTEM_USER) return false;
  return permissionOf(spec, user, entity)?.rowScope === "own";
}

export function canSeeField(spec: DaftarSpec, user: User, field: Pick<Field, "level">): boolean {
  if (user === SYSTEM_USER) return true;
  return (field.level ?? 0) <= (roleOf(spec, user)?.fieldLevel ?? 0);
}

export function visibleFields(spec: DaftarSpec, user: User, entity: Entity): Field[] {
  return entity.fields.filter((field) => canSeeField(spec, user, field));
}
