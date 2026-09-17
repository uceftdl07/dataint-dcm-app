import { describe, expect, it } from 'vitest';
import {
  buildPermissionsForRole,
  hasActiveProject,
  isPlatformAdmin,
  isProjectAdmin,
  platformRoleLabel,
  projectRoleFor,
  projectRoleLabel,
  projectScopeTypeLabel,
  projectStatusLabel,
} from './role-access';
import type { CurrentDcmUser, ProjectMembershipRef } from '../types/api';

function makeUser(overrides: Partial<CurrentDcmUser> = {}): CurrentDcmUser {
  return {
    id: 'user-1',
    entra_oid: 'oid-1',
    email: 'user@example.com',
    display_name: 'Test User',
    role: 'viewer',
    is_active: true,
    lz_ids: [],
    ...overrides,
  };
}

const membership = (over: Partial<ProjectMembershipRef> = {}): ProjectMembershipRef => ({
  project_id: 'proj-1',
  name: 'Project One',
  role: 'viewer',
  status: 'active',
  ...over,
});

describe('two-level project access matrix', () => {
  it('detects the platform admin from platform_role', () => {
    expect(isPlatformAdmin(makeUser({ platform_role: 'super_admin' }))).toBe(true);
    expect(isPlatformAdmin(makeUser({ platform_role: 'user' }))).toBe(false);
    expect(isPlatformAdmin(makeUser())).toBe(false);
    expect(isPlatformAdmin(null)).toBe(false);
  });

  it('resolves the caller role in a given project', () => {
    const user = makeUser({ projects: [membership({ role: 'admin' })] });
    expect(projectRoleFor(user, 'proj-1')).toBe('admin');
    expect(projectRoleFor(user, 'unknown')).toBeNull();
    expect(projectRoleFor(makeUser(), 'proj-1')).toBeNull();
  });

  it('grants project admin to platform admins and project admins only', () => {
    const platformAdmin = makeUser({ platform_role: 'super_admin' });
    const projectAdmin = makeUser({ projects: [membership({ role: 'admin' })] });
    const viewer = makeUser({ projects: [membership({ role: 'viewer' })] });

    expect(isProjectAdmin(platformAdmin, 'any-project')).toBe(true);
    expect(isProjectAdmin(projectAdmin, 'proj-1')).toBe(true);
    expect(isProjectAdmin(projectAdmin, 'proj-2')).toBe(false);
    expect(isProjectAdmin(viewer, 'proj-1')).toBe(false);
  });

  it('detects at least one active project', () => {
    expect(hasActiveProject(makeUser({ projects: [membership({ status: 'active' })] }))).toBe(true);
    expect(
      hasActiveProject(makeUser({ projects: [membership({ status: 'pending_validation' })] }))
    ).toBe(false);
    expect(hasActiveProject(makeUser())).toBe(false);
  });
});

describe('viewer reads every DCM data interface, scoped to their projects', () => {
  const dataPages = [
    'page:dashboard',
    'page:datafactory',
    'page:pipelines',
    'page:databricks',
    'page:databases',
    'page:clusters',
    'page:costs',
    'page:alerts',
    'page:security',
    'page:governance',
    'page:talk-to-data',
    'page:status',
    'page:projects',
    'page:settings',
  ];

  it('grants every data page to the viewer role', () => {
    const { pages } = buildPermissionsForRole('viewer');
    for (const page of dataPages) {
      expect(pages).toContain(page);
    }
  });

  it('never grants platform administration to the viewer role', () => {
    const { pages, features } = buildPermissionsForRole('viewer');
    expect(pages).not.toContain('page:users');
    expect(pages).not.toContain('page:admin');
    expect(features).not.toContain('feature:admin_ui');
  });

  it('withholds the unscopeable raw-table explorer from project members', () => {
    // The explorer reads an arbitrary catalog.schema.table, so the backend cannot
    // narrow it to a project scope and refuses it (require_unrestricted_scope).
    // Offering the entry point to a viewer would only produce a 403.
    expect(buildPermissionsForRole('viewer').pages).not.toContain('page:unity-catalog');
    expect(buildPermissionsForRole('data_architect').pages).not.toContain('page:unity-catalog');
    expect(buildPermissionsForRole('manager').pages).not.toContain('page:unity-catalog');
    expect(buildPermissionsForRole('admin').pages).toContain('page:unity-catalog');
    expect(buildPermissionsForRole('super_admin').pages).toContain('page:unity-catalog');
  });
});

describe('readable project labels (FR-017: names not ids)', () => {
  it('maps platform roles to labels', () => {
    expect(platformRoleLabel('super_admin')).toBe('Platform admin');
    expect(platformRoleLabel('user')).toBe('Member');
    expect(platformRoleLabel(undefined)).toBe('Member');
  });

  it('maps project roles to labels with an em dash fallback', () => {
    expect(projectRoleLabel('admin')).toBe('Project admin');
    expect(projectRoleLabel('viewer')).toBe('Project viewer');
    expect(projectRoleLabel(null)).toBe('—');
  });

  it('maps project statuses and scope types to labels', () => {
    expect(projectStatusLabel('pending_validation')).toBe('Pending validation');
    expect(projectStatusLabel('active')).toBe('Active');
    expect(projectScopeTypeLabel('lz')).toBe('Landing Zone');
    expect(projectScopeTypeLabel('dbx_workspace')).toBe('Databricks workspace');
  });
});
