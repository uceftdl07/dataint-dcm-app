import { driver, type Driver, type DriveStep } from 'driver.js';
import 'driver.js/dist/driver.css';
import './tour.css';

export interface RunTourOptions {
  steps: DriveStep[];
  onComplete?: () => void;
  onSkip?: () => void;
}

export function runTour({ steps, onComplete, onSkip }: RunTourOptions): Driver {
  const availableSteps = steps.filter((step) => {
    if (!step.element || typeof step.element !== 'string') return true;
    return document.querySelector(step.element);
  });

  let completed = false;

  const driverObj = driver({
    showProgress: true,
    animate: true,
    smoothScroll: true,
    allowClose: true,
    overlayOpacity: 0.55,
    stagePadding: 10,
    stageRadius: 14,
    popoverClass: 'dcm-tour-popover',
    nextBtnText: 'Next →',
    prevBtnText: '← Back',
    doneBtnText: 'Done ✓',
    progressText: '{{current}} of {{total}}',
    steps: availableSteps,
    onNextClick: () => {
      if (!driverObj.hasNextStep()) {
        completed = true;
      }
      driverObj.moveNext();
    },
    onDestroyed: () => {
      if (completed) {
        onComplete?.();
      } else {
        onSkip?.();
      }
    },
  });

  driverObj.drive();
  return driverObj;
}
