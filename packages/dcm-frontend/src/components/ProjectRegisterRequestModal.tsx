/**
 * ProjectRegisterRequestModal — self-service project creation from the login page.
 *
 * The visitor picks a Business Application from the public id+name catalog.
 * Landing-zone / Databricks scopes are attached server-side on register (never
 * exposed by the public reference API).
 */

import { AlertCircle, CheckCircle, Loader2, Plus, Send, Trash2, X } from 'lucide-react';
import React, { useMemo, useState } from 'react';
import { DcmApiError, registerProjectPublic } from '../api/dcmApiClient';
import { useReferenceBusinessApplications } from '../hooks/useProjectsQueries';
import { deriveBusinessAppOptions } from '../lib/project-registration';
import { Combobox } from './ui/combobox';
import { projectRoleLabel } from '../lib/role-access';
import type { ProjectRegisterMemberPayload, ProjectRole } from '../types/api';

interface ProjectRegisterRequestModalProps {
  onClose: () => void;
  /** Called when the BA already has a project — steers the visitor to Join. */
  onSwitchToJoin?: () => void;
  /** When set, the requester email is prefilled and locked (authenticated user). */
  defaultRequesterEmail?: string;
}

/** Role options exposed in the members list — exactly the two project roles. */
const MEMBER_ROLE_OPTIONS: ProjectRole[] = ['viewer', 'admin'];

interface MemberDraft {
  id: string;
  email: string;
  role: ProjectRole;
}

let memberIdCounter = 0;
const nextMemberId = (): string => `member-${(memberIdCounter += 1)}`;

export const ProjectRegisterRequestModal: React.FC<ProjectRegisterRequestModalProps> = ({
  onClose,
  onSwitchToJoin,
  defaultRequesterEmail,
}) => {
  const { data: referenceData } = useReferenceBusinessApplications();
  const baOptions = useMemo(
    () => deriveBusinessAppOptions(referenceData?.items ?? []),
    [referenceData]
  );
  const baComboboxOptions = useMemo(
    () => baOptions.map((o) => ({ value: o.businessAppId, label: o.label })),
    [baOptions]
  );

  const [requesterEmail, setRequesterEmail] = useState(defaultRequesterEmail ?? '');
  const [projectName, setProjectName] = useState('');
  const [businessAppId, setBusinessAppId] = useState('');
  const [members, setMembers] = useState<MemberDraft[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);

  const updateMember = (index: number, patch: Partial<MemberDraft>) => {
    setMembers((current) => current.map((m, i) => (i === index ? { ...m, ...patch } : m)));
  };

  const addMember = () =>
    setMembers((current) => [...current, { id: nextMemberId(), email: '', role: 'viewer' }]);

  const removeMember = (index: number) => {
    setMembers((current) => current.filter((_, i) => i !== index));
  };

  const normalizedEmail = requesterEmail.trim().toLowerCase();
  const canSubmit =
    normalizedEmail.includes('@') && projectName.trim().length > 0 && businessAppId.length > 0;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    if (!normalizedEmail.includes('@')) {
      setSubmitError('Please enter a valid professional email address');
      return;
    }
    if (projectName.trim().length === 0) {
      setSubmitError('Please enter a project name');
      return;
    }
    if (businessAppId.length === 0) {
      setSubmitError('Please select a Business Application');
      return;
    }

    const cleanedMembers: ProjectRegisterMemberPayload[] = members
      .map((m) => ({ email: m.email.trim().toLowerCase(), role: m.role }))
      .filter((m) => m.email.length > 0);

    const invalidMember = cleanedMembers.find((m) => !m.email.includes('@'));
    if (invalidMember) {
      setSubmitError('One or more member email addresses are invalid');
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);
    setConflict(false);

    try {
      await registerProjectPublic({
        businessAppId,
        name: projectName.trim(),
        members: cleanedMembers,
        // Scopes are resolved server-side from the BA referential.
        lzScope: [],
        dbxScope: [],
      });
      setSubmitSuccess(true);
      window.setTimeout(onClose, 3000);
    } catch (error) {
      if (error instanceof DcmApiError && error.statusCode === 409) {
        setConflict(true);
        setSubmitError(
          'A project already exists for this Business Application. Join the existing project instead.'
        );
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
          <h3 className="mb-2 text-center text-xl font-bold text-slate-900">Project registered</h3>
          <p className="text-center text-sm text-slate-600">
            Your project was created and is pending validation. An administrator will review it and
            contact you by email.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-[65] flex items-center justify-center bg-black/50 p-4">
      <div className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 p-6">
          <h2 className="text-xl font-bold text-slate-900">Register a project</h2>
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
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="register-email"
                  className="mb-2 block text-sm font-semibold text-slate-700"
                >
                  Your email <span className="text-red-500">*</span>
                </label>
                <input
                  id="register-email"
                  type="email"
                  value={requesterEmail}
                  onChange={(e) => setRequesterEmail(e.target.value)}
                  placeholder="jane.doe@totalenergies.com"
                  className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 disabled:bg-slate-100 disabled:text-slate-500"
                  disabled={isSubmitting || Boolean(defaultRequesterEmail)}
                  readOnly={Boolean(defaultRequesterEmail)}
                  required
                />
                <p className="mt-1 text-xs text-slate-500">You will be the project admin.</p>
              </div>
              <div>
                <label
                  htmlFor="register-name"
                  className="mb-2 block text-sm font-semibold text-slate-700"
                >
                  Project name <span className="text-red-500">*</span>
                </label>
                <input
                  id="register-name"
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="My data project"
                  className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                  disabled={isSubmitting}
                  required
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="register-business-app"
                className="mb-2 block text-sm font-semibold text-slate-700"
              >
                Business Application <span className="text-red-500">*</span>
              </label>
              <Combobox
                id="register-business-app"
                aria-label="Business Application"
                options={baComboboxOptions}
                value={businessAppId}
                onChange={setBusinessAppId}
                placeholder="Select a Business Application…"
                searchPlaceholder="Type a Business Application name…"
                typeToSearchMessage="Start typing to find a Business Application"
                emptyMessage="No Business Application matches your search."
                disabled={isSubmitting}
                required
              />
              <p className="mt-1 text-xs text-slate-500">
                Open the list, then type a name to filter — the full catalogue is not shown at once.
                Landing zones and Databricks workspaces for this Business Application are attached
                automatically when you register.
              </p>
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between gap-3">
                <p className="block text-sm font-semibold text-slate-700">Additional members</p>
                <button
                  type="button"
                  onClick={addMember}
                  className="flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-700"
                  disabled={isSubmitting}
                >
                  <Plus className="h-4 w-4" />
                  Add member
                </button>
              </div>
              {members.length === 0 ? (
                <p className="text-xs text-slate-500">
                  Optional — add teammates and pick their project role.
                </p>
              ) : (
                <div className="space-y-2">
                  {members.map((member, index) => (
                    <div key={member.id} className="flex gap-2">
                      <input
                        type="email"
                        value={member.email}
                        onChange={(e) => updateMember(index, { email: e.target.value })}
                        placeholder="teammate@totalenergies.com"
                        aria-label={`Member ${index + 1} email`}
                        className="flex-1 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                        disabled={isSubmitting}
                      />
                      <select
                        value={member.role}
                        onChange={(e) =>
                          updateMember(index, { role: e.target.value as ProjectRole })
                        }
                        aria-label={`Member ${index + 1} role`}
                        className="rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                        disabled={isSubmitting}
                      >
                        {MEMBER_ROLE_OPTIONS.map((role) => (
                          <option key={role} value={role}>
                            {projectRoleLabel(role)}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={() => removeMember(index)}
                        aria-label={`Remove member ${index + 1}`}
                        className="rounded-xl border border-slate-300 bg-white px-3 text-slate-400 hover:text-red-600"
                        disabled={isSubmitting}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {submitError && (
              <div className="flex flex-col gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
                <div className="flex items-start gap-2">
                  <AlertCircle className="h-5 w-5 flex-shrink-0" />
                  <span>{submitError}</span>
                </div>
                {conflict && onSwitchToJoin && (
                  <button
                    type="button"
                    onClick={onSwitchToJoin}
                    className="self-start rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700"
                  >
                    Join the existing project
                  </button>
                )}
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
                  Register project
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
