import type { DcmRole } from '../types/api';
import type { MenuChild, ModuleMenuItem } from '../config/navigation';

export function isSuperAdmin(role: DcmRole | null | undefined): boolean {
  return role === 'super_admin';
}

export function filterMenuChildren(
  children: MenuChild[],
  role: DcmRole | null | undefined
): MenuChild[] {
  return children
    .filter((child) => !child.requiresSuperAdmin || isSuperAdmin(role))
    .map((child) => {
      if (!child.children?.length) {
        return child;
      }
      return { ...child, children: filterMenuChildren(child.children, role) };
    })
    .filter((child) => !(child.collapsibleGroup && (child.children?.length ?? 0) === 0));
}

export function filterModuleMenu(
  menu: ModuleMenuItem[],
  role: DcmRole | null | undefined
): ModuleMenuItem[] {
  return menu.flatMap((item) => {
    if (!item.children) {
      return [item];
    }
    const children = filterMenuChildren(item.children, role);
    if (children.length === 0) {
      return [];
    }
    return [{ ...item, children }];
  });
}
