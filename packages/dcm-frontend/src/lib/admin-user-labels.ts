import type { DcmRole } from '../types/api';

export function formatRoleLabel(role: DcmRole): string {
  switch (role) {
    case 'pending':
      return 'Pending approval';
    case 'super_admin':
      return 'DCM Super Administrator';
    case 'admin':
      return 'DCM Administrator';
    case 'manager':
      return 'Business Manager';
    case 'data_architect':
      return 'Data Architect';
    default:
      return 'Read-only Viewer';
  }
}
