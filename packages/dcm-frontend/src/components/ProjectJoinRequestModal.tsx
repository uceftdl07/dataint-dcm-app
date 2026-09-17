/**
 * ProjectJoinRequestModal — self-service join request from the login page.
 *
 * The visitor is not yet a DCM user, so identity is a free-text email. The
 * requested role is always project viewer (backend default); the request is
 * routed to the project creator or admins for approval.
 */

import { AlertCircle, CheckCircle, Loader2, Send, X } from 'lucide-react';
import React, { useMemo, useState } from 'react';
import { DcmApiError, requestJoinProjectPublic } from '../api/dcmApiClient';
import {
  useReferenceBusinessApplications,
  useReferenceProjects,
} from '../hooks/useProjectsQueries';
import { Combobox } from './ui/combobox';

interface ProjectJoinRequestModalProps {
  onClose: () => void;
  /** Called when no project exists yet — steers the visitor to Register. */
  onSwitchToRegister?: () => void;
  /** When set, the requester email is prefilled and locked (authenticated user). */
  defaultRequesterEmail?: string;
}

export const ProjectJoinRequestModal: React.FC<ProjectJoinRequestModalProps> = ({
  onClose,
  onSwitchToRegister,
  defaultRequesterEmail,
}) => {
  const { data: referenceData } = useReferenceProjects();
  const { data: businessAppData } = useReferenceBusinessApplications();
  const projectOptions = useMemo(
    () => [...(referenceData?.items ?? [])].sort((a, b) => a.name.localeCompare(b.name)),
    [referenceData]
  );

  // Resolve each project's Business Application name so a visitor can also find
  // their project by BA rather than by project name.
  const baNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const ba of businessAppData?.items ?? []) {
      map.set(ba.businessApplicationId, ba.businessApplicationName || ba.businessApplicationId);
    }
    return map;
  }, [businessAppData]);

  const projectComboboxOptions = useMemo(
    () => projectOptions.map((p) => ({ value: p.id, label: p.name })),
    [projectOptions]
  );
  const businessAppComboboxOptions = useMemo(
    () =>
      [...projectOptions]
        .map((p) => ({ value: p.id, label: baNameById.get(p.businessAppId) ?? p.businessAppId }))
        .sort((a, b) => a.label.localeCompare(b.label)),
    [projectOptions, baNameById]
  );

  const [requesterEmail, setRequesterEmail] = useState(defaultRequesterEmail ?? '');
  const [searchMode, setSearchMode] = useState<'project' | 'business-app'>('project');
  const [projectId, setProjectId] = useState('');
  const [justification, setJustification] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const normalizedEmail = requesterEmail.trim().toLowerCase();
  const canSubmit = normalizedEmail.includes('@') && projectId.length > 0;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    if (!normalizedEmail.includes('@')) {
      setSubmitError('Please enter a valid professional email address');
      return;
    }
    if (projectId.length === 0) {
      setSubmitError('Please select a project to join');
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      await requestJoinProjectPublic({
        projectId,
        justification: justification.trim() || undefined,
      });
      setSubmitSuccess(true);
      window.setTimeout(onClose, 3000);
    } catch (error) {
      if (error instanceof DcmApiError && error.statusCode === 404) {
        setSubmitError('This project no longer exists. Refresh the list and try again.');
      } else {
        setSubmitError(error instanceof Error ? error.message : 'Error submitting request');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  if (submitSuccess) {
    return (
      <div className="fixed inset-0 z-[65] flex items-center justify-center bg-black/50 p-4">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-2xl">
          <div className="mb-4 flex justify-center">
            <div className="rounded-full bg-green-100 p-3">
              <CheckCircle className="h-12 w-12 text-green-600" />
            </div>
          </div>
          <h3 className="mb-2 text-center text-xl font-bold text-slate-900">Join request sent</h3>
          <p className="text-center text-sm text-slate-600">
            Your request was sent to the project admins for approval. You will be notified by email
            once it is reviewed.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-[65] flex items-center justify-center bg-black/50 p-4">
      <div className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 p-6">
          <h2 className="text-xl font-bold text-slate-900">Join a project</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
            aria-label="Close"
            disabled={isSubmitting}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6">
          <div className="space-y-5">
            <div>
              <label
                htmlFor="join-email"
                className="mb-2 block text-sm font-semibold text-slate-700"
              >
                Your email <span className="text-red-500">*</span>
              </label>
              <input
                id="join-email"
                type="email"
                value={requesterEmail}
                onChange={(e) => setRequesterEmail(e.target.value)}
                placeholder="jane.doe@totalenergies.com"
                className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 disabled:bg-slate-100 disabled:text-slate-500"
                disabled={isSubmitting || Boolean(defaultRequesterEmail)}
                readOnly={Boolean(defaultRequesterEmail)}
                required
              />
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <label
                  htmlFor={searchMode === 'project' ? 'join-project' : 'join-business-app'}
                  className="block text-sm font-semibold text-slate-700"
                >
                  {searchMode === 'project' ? 'Project' : 'Business Application'}{' '}
                  <span className="text-red-500">*</span>
                </label>
                <div className="inline-flex rounded-lg border border-slate-200 p-0.5 text-xs font-medium">
                  <button
                    type="button"
                    onClick={() => setSearchMode('project')}
                    aria-pressed={searchMode === 'project'}
                    className={
                      searchMode === 'project'
                        ? 'rounded-md bg-blue-600 px-2.5 py-1 text-white'
                        : 'rounded-md px-2.5 py-1 text-slate-500 hover:text-slate-700'
                    }
                  >
                    By project
                  </button>
                  <button
                    type="button"
                    onClick={() => setSearchMode('business-app')}
                    aria-pressed={searchMode === 'business-app'}
                    className={
                      searchMode === 'business-app'
                        ? 'rounded-md bg-blue-600 px-2.5 py-1 text-white'
                        : 'rounded-md px-2.5 py-1 text-slate-500 hover:text-slate-700'
                    }
                  >
                    By Business Application
                  </button>
                </div>
              </div>
              {searchMode === 'project' ? (
                <Combobox
                  id="join-project"
                  aria-label="Project"
                  options={projectComboboxOptions}
                  value={projectId}
                  onChange={setProjectId}
                  placeholder="Select a project…"
                  searchPlaceholder="Type a project name…"
                  typeToSearchMessage="Start typing to find a project"
                  emptyMessage="No project matches your search."
                  disabled={isSubmitting}
                  required
                />
              ) : (
                <Combobox
                  id="join-business-app"
                  aria-label="Business Application"
                  options={businessAppComboboxOptions}
                  value={projectId}
                  onChange={setProjectId}
                  placeholder="Select a Business Application…"
                  searchPlaceholder="Type a Business Application name…"
                  typeToSearchMessage="Start typing to find a Business Application"
                  emptyMessage="No Business Application matches your search."
                  disabled={isSubmitting}
                  required
                />
              )}
              {projectOptions.length === 0 && onSwitchToRegister && (
                <button
                  type="button"
                  onClick={onSwitchToRegister}
                  className="mt-2 text-xs font-semibold text-blue-600 hover:text-blue-700"
                >
                  No project yet — register one instead
                </button>
              )}
            </div>

            <div>
              <label
                htmlFor="join-justification"
                className="mb-2 block text-sm font-semibold text-slate-700"
              >
                Justification (optional)
              </label>
              <textarea
                id="join-justification"
                value={justification}
                onChange={(e) => setJustification(e.target.value)}
                placeholder="Why do you need access to this project?"
                rows={4}
                className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                disabled={isSubmitting}
              />
            </div>

            {submitError && (
              <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
                <AlertCircle className="h-5 w-5 flex-shrink-0" />
                <span>{submitError}</span>
              </div>
            )}
          </div>

          <div className="mt-6 flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-xl border border-slate-300 bg-white px-4 py-3 font-medium text-slate-700 transition-colors hover:bg-slate-50"
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-3 font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={isSubmitting || !canSubmit}
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Submitting…
                </>
              ) : (
                <>
                  <Send className="h-4 w-4" />
                  Request to join
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
