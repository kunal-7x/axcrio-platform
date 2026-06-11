/**
 * RBAC permission map (BUILD-SPEC §7.2 roles, §17 policy pre-check).
 *
 * Maps each role to a flat set of `resource:action` permission strings. GET /me/permissions
 * returns this so the dashboard gates UI and the policy layer pre-checks. The ledger's
 * `action:sign` permission is the gate for signing ActionPlans (P4).
 *
 * Owner ⊇ Admin ⊇ Marketer / Analyst / Approver (Approver = read + the sign right).
 */
import type { Role } from '@growth-os/auth';

export const ALL_PERMISSIONS = [
  'workspace:read',
  'workspace:create',
  'workspace:update',
  'member:read',
  'member:manage',
  'invite:create',
  'campaign:read',
  'campaign:create',
  'action:read',
  'action:propose',
  'action:sign',
  'policy:read',
  'policy:update',
  'flag:read',
  'flag:update',
  'notify:read',
  'notify:send',
  'billing:read',
] as const;

export type Permission = (typeof ALL_PERMISSIONS)[number];

const READ_ONLY: Permission[] = [
  'workspace:read',
  'member:read',
  'campaign:read',
  'action:read',
  'policy:read',
  'flag:read',
  'notify:read',
  'billing:read',
];

const MARKETER: Permission[] = [
  ...READ_ONLY,
  'campaign:create',
  'action:propose',
  'notify:send',
];

const APPROVER: Permission[] = [
  ...READ_ONLY,
  'action:propose',
  'action:sign', // the §17.2 approver right (the gate for signing money/destructive plans, P4)
];

const ADMIN: Permission[] = [
  ...MARKETER,
  ...APPROVER,
  'workspace:create',
  'workspace:update',
  'member:manage',
  'invite:create',
  'policy:update',
  'flag:update',
];

const OWNER: Permission[] = [...ADMIN];

const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  Owner: dedupe(OWNER),
  Admin: dedupe(ADMIN),
  Marketer: dedupe(MARKETER),
  Analyst: dedupe(READ_ONLY),
  Approver: dedupe(APPROVER),
};

/** Default autopilot ceiling per role (§17.1) — Owners/Admins may operate higher. */
const ROLE_AUTOPILOT_CEILING: Record<Role, 'L0' | 'L1' | 'L2' | 'L3' | 'L4'> = {
  Owner: 'L4',
  Admin: 'L3',
  Marketer: 'L2',
  Analyst: 'L0',
  Approver: 'L2',
};

export function permissionsForRole(role: Role): Permission[] {
  return ROLE_PERMISSIONS[role];
}

export function autopilotCeilingForRole(role: Role): 'L0' | 'L1' | 'L2' | 'L3' | 'L4' {
  return ROLE_AUTOPILOT_CEILING[role];
}

export function roleHasPermission(role: Role, perm: Permission): boolean {
  return ROLE_PERMISSIONS[role].includes(perm);
}

function dedupe(perms: Permission[]): Permission[] {
  return [...new Set(perms)];
}
