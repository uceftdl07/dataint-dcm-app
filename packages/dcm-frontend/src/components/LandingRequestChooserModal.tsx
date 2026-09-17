import { ArrowRight, FolderPlus, UserPlus, X } from 'lucide-react';
import React from 'react';

export type LandingRequestKind = 'project_register' | 'project_join';

interface LandingRequestChooserModalProps {
  onClose: () => void;
  onChoose: (kind: LandingRequestKind) => void;
}

export const LandingRequestChooserModal: React.FC<LandingRequestChooserModalProps> = ({
  onClose,
  onChoose,
}) => {
  return (
    <div className="fixed inset-0 z-[65] flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 p-6">
          <h2 className="text-xl font-bold text-slate-900">Join or register a project</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-3 p-6">
          <button
            type="button"
            onClick={() => onChoose('project_register')}
            className="group flex w-full items-start gap-4 rounded-xl border border-slate-200 bg-white p-4 text-left transition hover:border-[#0055A4]/35 hover:bg-blue-50/40"
          >
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-blue-100 text-[#0055A4]">
              <FolderPlus className="size-5" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-black text-slate-900">Register a project</span>
              <span className="mt-1 block text-xs text-slate-600">
                My project is not in DCM yet — I create it and become its admin.
              </span>
            </span>
            <ArrowRight className="mt-1 size-4 shrink-0 text-slate-400 transition group-hover:translate-x-0.5 group-hover:text-[#0055A4]" />
          </button>

          <button
            type="button"
            onClick={() => onChoose('project_join')}
            className="group flex w-full items-start gap-4 rounded-xl border border-slate-200 bg-white p-4 text-left transition hover:border-[#0055A4]/35 hover:bg-blue-50/40"
          >
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-indigo-100 text-indigo-700">
              <UserPlus className="size-5" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-black text-slate-900">Join a project</span>
              <span className="mt-1 block text-xs text-slate-600">
                My project already exists in DCM — I request to join it.
              </span>
            </span>
            <ArrowRight className="mt-1 size-4 shrink-0 text-slate-400 transition group-hover:translate-x-0.5 group-hover:text-[#0055A4]" />
          </button>
        </div>
      </div>
    </div>
  );
};
