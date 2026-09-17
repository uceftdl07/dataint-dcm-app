import clsx from 'clsx';
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Lock,
  LogOut,
  Moon,
  MoreVertical,
  Sun,
} from 'lucide-react';
import { useMsal } from '@azure/msal-react';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { flattenMenuLeaves, MAIN_MENU, SETTINGS_MENU, type MenuChild } from '../config/navigation';
import { filterModuleMenu } from '../lib/navigation-access';
import { ROUTE_PERMISSIONS } from '../config/role-permissions';
import { useTheme } from '../contexts/theme';
import { useCurrentDcmUser } from '../hooks/useCurrentDcmUser';
import { useComputeRecommendationsOpenCount } from '../hooks/useComputeRecommendationsOpenCount';
import { useRolePermissions } from '../hooks/useRolePermissions';
import { Badge } from './ui/badge';
import { useTour } from '../tour/TourContext';
import { cn } from '../lib/utils';
import { TotalEnergiesIcon } from './icons/te';

function getInitials(name: string) {
  return (
    name
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join('') || 'U'
  );
}

function CollapsedTooltip({ label, show }: { label: string; show: boolean }) {
  if (!show) return null;

  return (
    <span className="pointer-events-none absolute left-[calc(100%+0.75rem)] top-1/2 z-50 hidden -translate-y-1/2 whitespace-nowrap rounded-xl bg-popover px-3 py-1.5 text-xs font-semibold text-popover-foreground shadow-xl ring-1 ring-border group-hover:block group-focus-visible:block">
      {label}
    </span>
  );
}

function shouldCollapseSidebar() {
  return typeof window !== 'undefined' && window.innerWidth < 1180;
}

const Sidebar: React.FC = () => {
  const location = useLocation();
  const { instance, accounts } = useMsal();
  const { theme, toggleTheme } = useTheme();
  const { user } = useCurrentDcmUser();
  const { canAccess } = useRolePermissions();
  const { startWelcomeTour } = useTour();
  const { openCount: recommendationsOpenCount } = useComputeRecommendationsOpenCount();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(shouldCollapseSidebar);

  const isRouteLocked = useCallback(
    (path: string) => {
      const permissionKey = ROUTE_PERMISSIONS[path];
      return permissionKey ? !canAccess(permissionKey) : false;
    },
    [canAccess]
  );

  const menuItems = useMemo(() => filterModuleMenu(MAIN_MENU, user?.role), [user?.role]);
  const settingsItems = useMemo(() => filterModuleMenu(SETTINGS_MENU, user?.role), [user?.role]);
  const defaultExpanded = useMemo(() => {
    return menuItems.reduce<Record<string, boolean>>((acc, item) => {
      if (item.children) {
        const leaves = flattenMenuLeaves(item.children);
        acc[item.name] = leaves.some((child) => location.pathname === child.path);
        for (const child of item.children) {
          if (child.collapsibleGroup && child.children?.length) {
            const key = `${item.name}::${child.label}`;
            acc[key] = child.children.some((leaf) => location.pathname === leaf.path);
          }
        }
      }
      return acc;
    }, {});
  }, [location.pathname, menuItems]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>(defaultExpanded);

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined;

    const mediaQuery = window.matchMedia('(max-width: 1279px)');
    const syncSidebarWidth = () => setIsCollapsed(mediaQuery.matches);

    syncSidebarWidth();
    mediaQuery.addEventListener('change', syncSidebarWidth);

    return () => mediaQuery.removeEventListener('change', syncSidebarWidth);
  }, []);

  const handleToggle = (name: string) => {
    setExpanded((prev) => ({ ...prev, [name]: !prev[name] }));
  };

  const handleSectionToggle = (name: string) => {
    if (isCollapsed) {
      setIsCollapsed(false);
      setExpanded((prev) => ({ ...prev, [name]: true }));
      return;
    }

    handleToggle(name);
  };

  const handleLogout = async () => {
    try {
      await instance.logoutRedirect({ postLogoutRedirectUri: '/' });
    } catch (error) {
      console.error('Error during sign out:', error);
    }
  };

  const account = accounts[0];
  const userName = account?.name || 'Admin User';
  const userEmail = account?.username || 'admin@company.com';

  return (
    <aside
      data-tour="sidebar"
      className={cn(
        'sticky top-0 z-40 flex h-screen shrink-0 flex-col overflow-visible bg-sidebar/95 text-sidebar-foreground shadow-[12px_0_40px_rgba(15,23,42,0.06)] backdrop-blur-xl transition-[width] duration-300',
        isCollapsed ? 'w-[76px]' : 'w-[196px] lg:w-[216px] 2xl:w-[232px]'
      )}
    >
      <div className={cn('relative py-4', isCollapsed ? 'px-3' : 'px-3.5')}>
        <div
          className={cn(
            'flex items-center gap-2',
            isCollapsed
              ? 'h-14 justify-center p-0'
              : 'min-h-14 justify-start rounded-[1.25rem] bg-sidebar-accent/70 p-2.5'
          )}
        >
          <div
            className={cn(
              'flex shrink-0 items-center justify-center rounded-2xl bg-white shadow-lg shadow-primary/15',
              isCollapsed ? 'size-11' : 'size-10'
            )}
          >
            <TotalEnergiesIcon className={cn(isCollapsed ? 'h-6 w-8' : 'h-6 w-8')} />
          </div>
          <div className={clsx('min-w-0 flex-1', isCollapsed ? 'hidden' : 'block')}>
            <p className="leading-none" aria-label="Data connect">
              <span className="block text-[1.15rem] font-black tracking-[-0.04em] text-sidebar-foreground">
                Data
              </span>
              <span className="mt-0.5 block bg-gradient-to-r from-[#0055A4] via-[#00AEEF] to-[#ED1B2F] bg-clip-text text-[0.95rem] font-black tracking-[0.01em] text-transparent">
                connect
              </span>
            </p>
          </div>
          {!isCollapsed && (
            <button
              type="button"
              onClick={() => setIsCollapsed(true)}
              className="flex size-7 shrink-0 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-background hover:text-primary"
              aria-label="Collapse menu"
              title="Collapse menu"
            >
              <ChevronLeft size={16} />
            </button>
          )}
        </div>
        {isCollapsed && (
          <button
            type="button"
            onClick={() => setIsCollapsed(false)}
            className="absolute -right-3 top-1/2 flex size-8 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-background text-muted-foreground shadow-md transition-all hover:scale-105 hover:text-primary"
            aria-label="Expand menu"
            title="Expand menu"
          >
            <ChevronRight size={16} />
          </button>
        )}
      </div>

      <nav
        className={cn(
          'guardian-scrollbar flex-1 space-y-1 overflow-y-auto pb-4',
          isCollapsed ? 'px-2.5' : 'px-2.5'
        )}
      >
        {menuItems.map((item) => {
          const sectionLeaves = item.children ? flattenMenuLeaves(item.children) : [];
          const sectionLocked = item.children
            ? sectionLeaves.every((child) => isRouteLocked(child.path))
            : 'path' in item && item.path
              ? isRouteLocked(item.path)
              : item.requiresAdmin
                ? !canAccess('page:admin')
                : false;
          const sectionActive = sectionLeaves.some((child) => location.pathname === child.path);

          const renderLeafLink = (child: MenuChild) => {
            const locked = isRouteLocked(child.path);
            const showRecoBadge =
              child.path === '/databricks/compute/recommendations' && recommendationsOpenCount > 0;
            return (
              <NavLink
                key={child.path}
                to={child.path}
                className={({ isActive }) =>
                  clsx(
                    'flex items-center gap-2 rounded-lg px-3 py-1.5 text-[0.8125rem] font-medium leading-5 transition-all',
                    locked && 'opacity-45 grayscale',
                    isActive
                      ? 'bg-sidebar-accent font-semibold text-sidebar-accent-foreground hover:bg-sidebar-accent active:bg-sidebar-accent'
                      : 'text-sidebar-foreground/75 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground active:bg-sidebar-accent active:text-sidebar-accent-foreground'
                  )
                }
                title={locked ? `${child.label} — restricted for your role` : child.label}
              >
                <span className="min-w-0 flex-1 truncate">{child.label}</span>
                {showRecoBadge ? (
                  <Badge variant="warning" className="ml-auto shrink-0 px-1.5 py-0 text-[10px]">
                    {recommendationsOpenCount > 99 ? '99+' : recommendationsOpenCount}
                  </Badge>
                ) : null}
                {locked && <Lock size={11} className="ml-auto shrink-0 text-amber-600/80" />}
              </NavLink>
            );
          };

          return item.children ? (
            <div key={item.name}>
              <button
                className={cn(
                  'group relative flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2.5 text-sm font-semibold tracking-[-0.01em] transition-all',
                  isCollapsed ? 'justify-center' : 'justify-start',
                  sectionLocked && 'opacity-45 grayscale',
                  sectionActive
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground shadow-inner hover:bg-sidebar-accent active:bg-sidebar-accent'
                    : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground active:bg-sidebar-accent active:text-sidebar-accent-foreground'
                )}
                onClick={() => handleSectionToggle(item.name)}
                aria-expanded={Boolean(expanded[item.name])}
                aria-label={`${item.name}, ${expanded[item.name] ? 'collapse' : 'expand'} submenu`}
                title={`${expanded[item.name] ? 'Collapse' : 'Expand'} ${item.name}`}
              >
                <item.icon size={17} className="shrink-0" />
                <span className={clsx('flex-1 text-left', isCollapsed ? 'hidden' : 'block')}>
                  {item.name}
                </span>
                {sectionLocked && !isCollapsed && (
                  <Lock size={12} className="shrink-0 text-amber-600/80" aria-hidden />
                )}
                <ChevronDown
                  size={14}
                  aria-hidden
                  className={clsx(
                    'shrink-0 text-sidebar-foreground/60 transition-transform',
                    isCollapsed ? 'hidden' : 'block',
                    expanded[item.name] && 'rotate-180'
                  )}
                />
                <CollapsedTooltip label={item.name} show={isCollapsed} />
              </button>
              {expanded[item.name] && !isCollapsed && (
                <div className="ml-5 mt-1 space-y-1 pl-2">
                  {item.children.map((child) => {
                    if (child.collapsibleGroup && child.children?.length) {
                      const groupKey = `${item.name}::${child.label}`;
                      const groupOpen = Boolean(expanded[groupKey]);
                      const groupActive = child.children.some(
                        (leaf) => location.pathname === leaf.path
                      );
                      return (
                        <div key={child.label} className="space-y-1">
                          <button
                            type="button"
                            className={clsx(
                              'flex w-full items-center gap-1 rounded-lg px-3 py-1.5 text-[0.8125rem] font-semibold tracking-[-0.01em] transition-all',
                              groupActive
                                ? 'text-sidebar-accent-foreground'
                                : 'text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
                            )}
                            onClick={() => handleSectionToggle(groupKey)}
                            aria-expanded={groupOpen}
                            aria-label={`${child.label}, ${groupOpen ? 'collapse' : 'expand'} submenu`}
                          >
                            <span className="flex-1 text-left">{child.label}</span>
                            <ChevronDown
                              size={12}
                              aria-hidden
                              className={clsx(
                                'shrink-0 text-sidebar-foreground/50 transition-transform',
                                groupOpen && 'rotate-180'
                              )}
                            />
                          </button>
                          {groupOpen && (
                            <div className="ml-2 space-y-1 border-l border-sidebar-border/60 pl-2">
                              {child.children.map((leaf) => renderLeafLink(leaf))}
                            </div>
                          )}
                        </div>
                      );
                    }

                    if (child.isGroupHeader) {
                      return (
                        <p
                          key={child.label}
                          className="px-3 pb-1 pt-2 text-[0.7rem] font-semibold tracking-[-0.01em] text-muted-foreground/70"
                          aria-hidden
                        >
                          {child.label}
                        </p>
                      );
                    }

                    return renderLeafLink(child);
                  })}
                </div>
              )}
            </div>
          ) : (
            <NavLink
              key={item.name}
              to={item.path!}
              className={({ isActive }) =>
                clsx(
                  'group relative flex items-center gap-2.5 rounded-xl px-2.5 py-2.5 text-sm font-semibold tracking-[-0.01em] transition-all',
                  isCollapsed ? 'justify-center' : 'justify-start',
                  sectionLocked && 'opacity-45 grayscale',
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground shadow-inner hover:bg-sidebar-accent active:bg-sidebar-accent'
                    : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground active:bg-sidebar-accent active:text-sidebar-accent-foreground'
                )
              }
              aria-label={item.name}
              title={sectionLocked ? `${item.name} — restricted for your role` : item.name}
            >
              <item.icon size={17} className="shrink-0" />
              <span className={clsx(isCollapsed ? 'hidden' : 'inline')}>{item.name}</span>
              {sectionLocked && !isCollapsed && (
                <Lock size={12} className="ml-auto shrink-0 text-amber-600/80" />
              )}
              <CollapsedTooltip label={item.name} show={isCollapsed} />
            </NavLink>
          );
        })}
      </nav>

      {/* Settings section */}
      <div className="px-2.5 pb-1" data-testid="sidebar-settings">
        <hr className="mb-2 border-border/50" />
        {!isCollapsed && (
          <p className="px-2.5 pb-1 text-[0.65rem] font-bold uppercase tracking-widest text-muted-foreground/60">
            Settings
          </p>
        )}
        {settingsItems.map((item) => {
          if (item.requiresAdmin && !canAccess('page:admin')) {
            return null;
          }
          if (item.children || !('path' in item) || !item.path) {
            return null;
          }

          return (
            <NavLink
              key={item.name}
              to={item.path}
              className={({ isActive }) =>
                clsx(
                  'group relative flex items-center gap-2.5 rounded-xl px-2.5 py-2.5 text-sm font-semibold tracking-[-0.01em] transition-all',
                  isCollapsed ? 'justify-center' : 'justify-start',
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground shadow-inner hover:bg-sidebar-accent active:bg-sidebar-accent'
                    : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground active:bg-sidebar-accent active:text-sidebar-accent-foreground'
                )
              }
              aria-label={item.name}
              title={item.name}
            >
              <item.icon size={17} className="shrink-0" />
              <span className={clsx(isCollapsed ? 'hidden' : 'inline')}>{item.name}</span>
              <CollapsedTooltip label={item.name} show={isCollapsed} />
            </NavLink>
          );
        })}
      </div>

      <div className="relative p-2">
        <button
          onClick={() => setShowUserMenu((value) => !value)}
          data-state={showUserMenu ? 'open' : 'closed'}
          className={cn(
            'group flex w-full items-center gap-2 overflow-hidden rounded-md p-2 text-left text-sm transition-[width,height,padding]',
            'hover:bg-sidebar-accent hover:text-sidebar-accent-foreground active:bg-sidebar-accent active:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            'data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground',
            isCollapsed ? 'relative mx-auto size-10 justify-center p-0' : 'h-12'
          )}
          aria-expanded={showUserMenu}
          aria-haspopup="menu"
          aria-label="Account menu — theme and sign out"
          title="Account menu"
        >
          <div className="flex w-full items-center gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--tdf-pink)] text-sm font-semibold text-white">
              {getInitials(userName)}
            </div>
            <div
              className={clsx(
                'min-w-0 flex-1 text-left text-sm leading-tight',
                isCollapsed ? 'hidden' : 'grid'
              )}
            >
              <span className="truncate font-medium text-sidebar-foreground">{userName}</span>
              <span className="truncate text-xs text-sidebar-foreground/70">{userEmail}</span>
              {user?.role && (
                <span className="truncate text-[10px] font-semibold uppercase tracking-wider text-amber-700">
                  Role: {user.role}
                </span>
              )}
            </div>
            <span
              className={clsx(
                'flex shrink-0 items-center justify-center rounded-md text-sidebar-foreground/70 transition-colors group-hover:bg-background/80 group-hover:text-sidebar-accent-foreground group-data-[state=open]:bg-background/80 group-data-[state=open]:text-sidebar-accent-foreground',
                isCollapsed
                  ? 'absolute -bottom-0.5 -right-0.5 size-5 bg-sidebar shadow-sm ring-1 ring-border'
                  : 'ml-auto size-7'
              )}
              aria-hidden
            >
              <MoreVertical size={isCollapsed ? 12 : 16} />
            </span>
          </div>
        </button>

        {showUserMenu && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setShowUserMenu(false)} />
            <div className="absolute bottom-20 left-3 z-50 w-72 overflow-hidden rounded-lg bg-popover p-2 text-popover-foreground shadow-2xl shadow-slate-950/20 ring-1 ring-border md:left-4">
              <div className="flex items-center gap-3 rounded-lg bg-muted p-3">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-[var(--tdf-pink)] text-sm font-semibold text-white">
                  {getInitials(userName)}
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-foreground">{userName}</p>
                  <p className="truncate text-xs text-muted-foreground">{userEmail}</p>
                </div>
              </div>

              <div className="mt-2 space-y-1">
                <button
                  type="button"
                  onClick={() => {
                    setShowUserMenu(false);
                    startWelcomeTour();
                  }}
                  className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium text-popover-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                  title="Guide to visit DCM — replay the interactive tour"
                >
                  <CircleHelp size={17} />
                  <span>Guide to visit DCM</span>
                </button>
                <button
                  onClick={() => {
                    toggleTheme();
                    setShowUserMenu(false);
                  }}
                  className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium text-popover-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                >
                  {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
                  <span>{theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}</span>
                </button>
                <button
                  onClick={handleLogout}
                  className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium text-popover-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                >
                  <LogOut size={17} />
                  <span>Sign out</span>
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </aside>
  );
};

export default Sidebar;
