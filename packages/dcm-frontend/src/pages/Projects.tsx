import { FolderKanban, Plus, UserPlus } from 'lucide-react';
import { useCallback, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { PageError } from '../components/domain';
import {
  Content,
  ContentActions,
  ContentDescription,
  ContentHeader,
  ContentMain,
} from '../components/layout/content';
import { ProjectJoinRequestModal } from '../components/ProjectJoinRequestModal';
import { ProjectRegisterRequestModal } from '../components/ProjectRegisterRequestModal';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Skeleton } from '../components/ui/skeleton';
import { useCurrentDcmUser } from '../hooks/useCurrentDcmUser';
import { useProjectsList } from '../hooks/useProjectsQueries';
import { currentUserQueryKeys, projectsQueryKeys } from '../hooks/query-keys';
import {
  isPlatformAdmin,
  platformRoleLabel,
  projectRoleLabel,
  projectStatusLabel,
  projectStatusVariant,
} from '../lib/role-access';
import type { ProjectSummary } from '../types/api';

function ProjectListItem({ project }: { project: ProjectSummary }) {
  return (
    <Card interactive>
      <Link to={`/projects/${encodeURIComponent(project.id)}`} className="block">
        <CardHeader className="gap-2">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1 space-y-1">
              <CardTitle className="truncate">{project.name}</CardTitle>
              <CardDescription
                className="truncate font-mono text-[11px]"
                title={project.businessAppId}
              >
                {project.businessAppId}
              </CardDescription>
            </div>
            <Badge variant={projectStatusVariant(project.status)} className="shrink-0">
              {projectStatusLabel(project.status)}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-1.5 pt-0">
          <Badge variant="outline">{projectRoleLabel(project.role)}</Badge>
          {/* What the project grants, straight from the list payload. */}
          <Badge variant="secondary" title={project.lzScope.join(', ')}>
            {project.lzScope.length} LZ
          </Badge>
          <Badge variant="secondary" title={project.dbxScope.join(', ')}>
            {project.dbxScope.length} workspace{project.dbxScope.length === 1 ? '' : 's'}
          </Badge>
          <Badge variant="secondary">
            {project.memberCount} member{project.memberCount === 1 ? '' : 's'}
          </Badge>
        </CardContent>
      </Link>
    </Card>
  );
}

export default function Projects() {
  const { user } = useCurrentDcmUser();
  const queryClient = useQueryClient();
  const projectsQuery = useProjectsList();
  const [panel, setPanel] = useState<'none' | 'create' | 'join'>('none');

  const platformAdmin = isPlatformAdmin(user);
  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data]);
  const visibleProjects = platformAdmin
    ? projects.filter((p) => p.status !== 'pending_validation')
    : projects;

  /**
   * The register/join modals post to the self-service routes themselves, so
   * nothing invalidates the caches for us: refresh the list and `/auth/me` on
   * close so a project registered from here shows up straight away.
   */
  const closePanel = useCallback(() => {
    setPanel('none');
    void queryClient.invalidateQueries({ queryKey: projectsQueryKeys.list() });
    void queryClient.invalidateQueries({ queryKey: currentUserQueryKeys.me() });
  }, [queryClient]);

  return (
    <Content>
      <ContentHeader>
        <ContentDescription>
          Your projects and their two-level access — platform role{' '}
          <strong>{platformRoleLabel(user?.platform_role)}</strong> combined with your role in each
          project.
        </ContentDescription>
        <ContentActions className="flex gap-3">
          <Button onClick={() => setPanel('create')}>
            <Plus /> Create project
          </Button>
          <Button variant="outline" onClick={() => setPanel('join')}>
            <UserPlus /> Join project
          </Button>
        </ContentActions>
      </ContentHeader>

      <ContentMain>
        {projectsQuery.isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-28 w-full" />
            ))}
          </div>
        ) : projectsQuery.isError ? (
          <div className="flex flex-col gap-3">
            <PageError message="Unable to load your projects." />
            <Button variant="outline" onClick={() => void projectsQuery.refetch()}>
              Retry
            </Button>
          </div>
        ) : visibleProjects.length === 0 ? (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FolderKanban size={16} /> No project yet
              </CardTitle>
              <CardDescription>
                You don&apos;t belong to any project. Create one for a Business Application, or
                request to join an existing project to see its monitoring data.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex gap-3">
              <Button onClick={() => setPanel('create')}>
                <Plus /> Create a project
              </Button>
              <Button variant="outline" onClick={() => setPanel('join')}>
                <UserPlus /> Join a project
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {visibleProjects.map((project) => (
              <ProjectListItem key={project.id} project={project} />
            ))}
          </div>
        )}
      </ContentMain>

      {/*
        Same forms as the login page (feature 016): the Business Application
        catalog with its landing-zone / workspace suggestions, the members list
        and the register↔join hand-off. Signed in here, so the requester email is
        prefilled and locked — the backend derives it from the token either way.
      */}
      {panel === 'create' && (
        <ProjectRegisterRequestModal
          defaultRequesterEmail={user?.email ?? undefined}
          onClose={closePanel}
          onSwitchToJoin={() => setPanel('join')}
        />
      )}
      {panel === 'join' && (
        <ProjectJoinRequestModal
          defaultRequesterEmail={user?.email ?? undefined}
          onClose={closePanel}
          onSwitchToRegister={() => setPanel('create')}
        />
      )}
    </Content>
  );
}
