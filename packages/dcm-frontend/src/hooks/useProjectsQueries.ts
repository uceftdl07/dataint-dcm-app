import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import {
  DcmApiError,
  addProjectMember,
  createProject,
  createProjectJoinRequest,
  createProjectScopeRequest,
  decideProjectJoinRequest,
  decideScopeRequest,
  deleteProject,
  getProject,
  listAllJoinRequests,
  listProjectJoinRequests,
  listProjectMembers,
  listProjects,
  listReferenceBusinessApplications,
  listReferenceProjects,
  listScopeRequests,
  rejectProject,
  removeProjectMember,
  updateProjectMemberRole,
  validateProject,
} from '../api/dcmApiClient';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';
import { currentUserQueryKeys, projectsQueryKeys } from './query-keys';
import type {
  ProjectCreatePayload,
  ProjectJoinRequestCreatePayload,
  ProjectMemberAddPayload,
  ProjectRejectPayload,
  ProjectRequestDecisionPayload,
  ProjectRole,
  ProjectScopeRequestCreatePayload,
} from '../types/api';

/** Backend routes (T002) may not be deployed yet: treat a 404 collection as empty. */
async function emptyOn404<T>(promise: Promise<T[]>): Promise<T[]> {
  try {
    return await promise;
  } catch (error) {
    if (error instanceof DcmApiError && error.statusCode === 404) {
      return [];
    }
    throw error;
  }
}

export function useProjectsList(enabled = true) {
  return useQuery({
    queryKey: projectsQueryKeys.list(),
    queryFn: () => emptyOn404(listProjects()),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled,
  });
}

export function useProjectDetail(projectId: string, enabled = true) {
  return useQuery({
    queryKey: projectsQueryKeys.detail(projectId),
    queryFn: () => getProject(projectId),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled: enabled && Boolean(projectId),
  });
}

export function useProjectMembers(projectId: string, enabled = true) {
  return useQuery({
    queryKey: projectsQueryKeys.members(projectId),
    queryFn: () => listProjectMembers(projectId),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled: enabled && Boolean(projectId),
  });
}

export function useProjectJoinRequests(projectId: string, enabled = true) {
  return useQuery({
    queryKey: projectsQueryKeys.joinRequests(projectId),
    queryFn: () => listProjectJoinRequests(projectId),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled: enabled && Boolean(projectId),
  });
}

/**
 * Platform-admin queue of pending join requests across every project — a
 * request is never stuck behind a project admin who never signs in.
 */
export function useAllJoinRequests(enabled = true) {
  return useQuery({
    queryKey: projectsQueryKeys.allJoinRequests(),
    queryFn: () => emptyOn404(listAllJoinRequests()),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled,
  });
}

export function useScopeRequests(enabled = true) {
  return useQuery({
    queryKey: projectsQueryKeys.scopeRequests(),
    queryFn: () => emptyOn404(listScopeRequests()),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled,
  });
}

/**
 * Public Business-Application catalog (id + name) for register/join forms.
 * LZ / workspace inventory is never returned here — resolved on register.
 */
export function useReferenceBusinessApplications(enabled = true) {
  return useQuery({
    queryKey: projectsQueryKeys.referenceBusinessApplications(),
    queryFn: listReferenceBusinessApplications,
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled,
  });
}

/**
 * Public catalog of joinable DCM projects (`dcm_projects`, pending/active)
 * backing the login "Join a project" form. Public (skipAuth) source.
 */
export function useReferenceProjects(enabled = true) {
  return useQuery({
    queryKey: projectsQueryKeys.referenceProjects(),
    queryFn: listReferenceProjects,
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    enabled,
  });
}

/**
 * Imperative project actions that invalidate the affected caches on success.
 * Callers await these and surface success/error toasts (mirrors the Admin page pattern).
 */
export function useProjectActions() {
  const queryClient = useQueryClient();

  const invalidateList = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: projectsQueryKeys.list() });
    void queryClient.invalidateQueries({ queryKey: currentUserQueryKeys.me() });
  }, [queryClient]);

  return {
    create: useCallback(
      async (payload: ProjectCreatePayload) => {
        const project = await createProject(payload);
        invalidateList();
        return project;
      },
      [invalidateList]
    ),
    validate: useCallback(
      async (projectId: string) => {
        const project = await validateProject(projectId);
        invalidateList();
        void queryClient.invalidateQueries({ queryKey: projectsQueryKeys.detail(projectId) });
        void queryClient.invalidateQueries({ queryKey: projectsQueryKeys.members(projectId) });
        return project;
      },
      [invalidateList, queryClient]
    ),
    reject: useCallback(
      async (projectId: string, payload: ProjectRejectPayload) => {
        const project = await rejectProject(projectId, payload);
        invalidateList();
        void queryClient.invalidateQueries({ queryKey: projectsQueryKeys.detail(projectId) });
        return project;
      },
      [invalidateList, queryClient]
    ),
    remove: useCallback(
      async (projectId: string) => {
        await deleteProject(projectId);
        invalidateList();
        // The project took its members and its open requests with it, so the two
        // platform-wide queues on the same screen are stale as well.
        void queryClient.invalidateQueries({ queryKey: projectsQueryKeys.detail(projectId) });
        void queryClient.invalidateQueries({ queryKey: projectsQueryKeys.allJoinRequests() });
        void queryClient.invalidateQueries({ queryKey: projectsQueryKeys.scopeRequests() });
      },
      [invalidateList, queryClient]
    ),
    changeMemberRole: useCallback(
      async (projectId: string, userId: string, role: ProjectRole) => {
        const member = await updateProjectMemberRole(projectId, userId, role);
        void queryClient.invalidateQueries({ queryKey: projectsQueryKeys.members(projectId) });
        return member;
      },
      [queryClient]
    ),
    addMember: useCallback(
      async (projectId: string, payload: ProjectMemberAddPayload) => {
        const member = await addProjectMember(projectId, payload);
        void queryClient.invalidateQueries({ queryKey: projectsQueryKeys.members(projectId) });
        return member;
      },
      [queryClient]
    ),
    removeMember: useCallback(
      async (projectId: string, userId: string) => {
        await removeProjectMember(projectId, userId);
        void queryClient.invalidateQueries({ queryKey: projectsQueryKeys.members(projectId) });
      },
      [queryClient]
    ),
    requestJoin: useCallback(
      async (projectId: string, payload: ProjectJoinRequestCreatePayload) => {
        const request = await createProjectJoinRequest(projectId, payload);
        return request;
      },
      []
    ),
    decideJoin: useCallback(
      async (projectId: string, requestId: string, payload: ProjectRequestDecisionPayload) => {
        const request = await decideProjectJoinRequest(requestId, payload);
        void queryClient.invalidateQueries({ queryKey: projectsQueryKeys.joinRequests(projectId) });
        void queryClient.invalidateQueries({ queryKey: projectsQueryKeys.allJoinRequests() });
        void queryClient.invalidateQueries({ queryKey: projectsQueryKeys.members(projectId) });
        void queryClient.invalidateQueries({ queryKey: projectsQueryKeys.list() });
        return request;
      },
      [queryClient]
    ),
    requestScope: useCallback(
      async (projectId: string, payload: ProjectScopeRequestCreatePayload) => {
        // One row per requested item, all sharing the submission's `requestedAt`.
        const requests = await createProjectScopeRequest(projectId, payload);
        void queryClient.invalidateQueries({ queryKey: projectsQueryKeys.scopeRequests() });
        return requests;
      },
      [queryClient]
    ),
    decideScope: useCallback(
      async (requestId: string, payload: ProjectRequestDecisionPayload) => {
        const request = await decideScopeRequest(requestId, payload);
        void queryClient.invalidateQueries({ queryKey: projectsQueryKeys.scopeRequests() });
        return request;
      },
      [queryClient]
    ),
  };
}
