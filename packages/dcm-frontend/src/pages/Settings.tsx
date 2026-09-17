import {
  CheckCircle2,
  CircleHelp,
  RefreshCw,
  RotateCcw,
  Settings as SettingsIcon,
  ShieldCheck,
} from 'lucide-react';
import React from 'react';
import { useTour } from '../tour/TourContext';
import {
  Content,
  ContentActions,
  ContentDescription,
  ContentHeader,
  ContentMain,
  ContentTitle,
} from '../components/layout/content';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { StatusBadge } from '../components/ui/status';
import { NotificationPreferencesCard } from '../components/settings/NotificationPreferencesCard';
import { useTheme } from '../contexts/theme';
import { useHealthQuery } from '../hooks/useHealthQuery';

const Settings: React.FC = () => {
  const { theme, toggleTheme } = useTheme();
  const { health, loading, error, refetch, isFetching } = useHealthQuery();
  const { startPageTour, startWelcomeTour, resetTours } = useTour();

  return (
    <Content>
      <ContentHeader>
        <div>
          <div className="sr-only">
            <div className="rounded-xl bg-primary p-2 text-primary-foreground">
              <SettingsIcon size={20} />
            </div>
            <ContentTitle>Settings</ContentTitle>
          </div>
          <ContentDescription>
            Guardian UI preferences and backend connection status
          </ContentDescription>
        </div>
        <ContentActions>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void refetch()}
            disabled={isFetching}
          >
            <RefreshCw />
            Test backend
          </Button>
        </ContentActions>
      </ContentHeader>

      <ContentMain>
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Theme</CardTitle>
              <CardDescription>Guardian dark/light mode compatibility</CardDescription>
            </CardHeader>
            <CardContent className="flex items-center justify-between gap-4">
              <div>
                <p className="font-medium capitalize">{theme}</p>
                <p className="text-sm text-muted-foreground">
                  The choice is persisted in the browser.
                </p>
              </div>
              <Button onClick={toggleTheme}>Toggle</Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Backend DCM</CardTitle>
              <CardDescription>Real healthcheck `/api/v1/health`</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {error ? (
                <p className="text-sm text-destructive">{error}</p>
              ) : health ? (
                <>
                  <div className="flex items-center justify-between rounded-xl border p-3">
                    <span className="text-sm text-muted-foreground">Service</span>
                    <span className="font-medium">{health.service}</span>
                  </div>
                  <div className="flex items-center justify-between rounded-xl border p-3">
                    <span className="text-sm text-muted-foreground">API</span>
                    <StatusBadge value={health.status === 'ok' ? 'succeeded' : 'failed'} />
                  </div>
                  <div className="flex items-center justify-between rounded-xl border p-3">
                    <span className="text-sm text-muted-foreground">Database</span>
                    <StatusBadge value={health.database === 'ok' ? 'succeeded' : 'failed'} />
                  </div>
                </>
              ) : loading ? (
                <p className="text-sm text-muted-foreground">Loading...</p>
              ) : null}
            </CardContent>
          </Card>
        </div>

        <NotificationPreferencesCard />

        <Card data-tour="settings-guided-tours">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CircleHelp size={18} className="text-primary" />
              Guided tours
            </CardTitle>
            <CardDescription>
              Interactive walkthroughs with animated highlights. Replay anytime — each page has its
              own tour.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" onClick={() => startPageTour('settings')}>
              Replay this page
            </Button>
            <Button variant="secondary" size="sm" onClick={() => startWelcomeTour()}>
              Replay welcome tour
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                resetTours();
                window.location.assign('/dashboard');
              }}
            >
              <RotateCcw size={14} />
              Reset all tours
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardDescription>Reference system applied to the DCM frontend</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-3">
            <div className="rounded-xl border p-3">
              <CheckCircle2 className="mb-2 text-tdf-green" />
              <p className="font-medium">Tokens TotalEnergies</p>
              <p className="text-sm text-muted-foreground">
                Palette `--tdf-*`, surfaces and rings.
              </p>
            </div>
            <div className="rounded-xl border p-3">
              <ShieldCheck className="mb-2 text-primary" />
              <p className="font-medium">Accessibility</p>
              <p className="text-sm text-muted-foreground">
                Visible focus, alternative text, and explicit states.
              </p>
            </div>
            <div className="rounded-xl border p-3">
              <SettingsIcon className="mb-2 text-primary" />
              <p className="font-medium">Components UI</p>
              <p className="text-sm text-muted-foreground">
                Card, Table, Badge, Button, Alert, Tabs.
              </p>
            </div>
          </CardContent>
        </Card>
      </ContentMain>
    </Content>
  );
};

export default Settings;
