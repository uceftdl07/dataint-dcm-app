import React, { useState } from 'react';
import { LandingRequestChooserModal, type LandingRequestKind } from '../LandingRequestChooserModal';
import { ProjectJoinRequestModal } from '../ProjectJoinRequestModal';
import { ProjectRegisterRequestModal } from '../ProjectRegisterRequestModal';
import { LandingAccessCta } from './LandingAccessCta';
import './landing-coach.css';

type LandingRequestStep = 'idle' | 'chooser' | LandingRequestKind;

/** Landing CTA — join or register a DCM project (no manual DCM access request). */
export const LandingAccessGuide: React.FC = () => {
  const [step, setStep] = useState<LandingRequestStep>('idle');

  const close = () => setStep('idle');

  return (
    <>
      <LandingAccessCta onOpenForm={() => setStep('chooser')} />

      {step === 'chooser' && (
        <LandingRequestChooserModal onClose={close} onChoose={(kind) => setStep(kind)} />
      )}

      {step === 'project_register' && (
        <ProjectRegisterRequestModal
          onClose={close}
          onSwitchToJoin={() => setStep('project_join')}
        />
      )}

      {step === 'project_join' && (
        <ProjectJoinRequestModal
          onClose={close}
          onSwitchToRegister={() => setStep('project_register')}
        />
      )}
    </>
  );
};
