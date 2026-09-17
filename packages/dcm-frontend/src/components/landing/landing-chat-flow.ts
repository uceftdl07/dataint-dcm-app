export type ChatChoiceId = 'no-access' | 'need-lz' | 'exploring' | 'start-over';

export interface ChatChoice {
  id: ChatChoiceId;
  label: string;
}

export interface ChatMessage {
  id: string;
  role: 'bot' | 'user';
  text: string;
  delayMs?: number;
}

export type ChatPhase =
  | 'greeting'
  | 'no-access'
  | 'need-lz'
  | 'exploring'
  | 'done';

export const GREETING_MESSAGES: ChatMessage[] = [
  {
    id: 'greet-1',
    role: 'bot',
    text: "Hey! I'm DataIQ — your DCM onboarding buddy.",
    delayMs: 0,
  },
  {
    id: 'greet-2',
    role: 'bot',
    text: 'No DCM access yet, or stuck on a landing zone? I can walk you through it in under a minute.',
    delayMs: 700,
  },
];

export const ROOT_CHOICES: ChatChoice[] = [
  { id: 'no-access', label: "I don't have DCM access yet" },
  { id: 'need-lz', label: 'I have DCM but need a landing zone' },
  { id: 'exploring', label: "I'm just exploring" },
];

export const NO_ACCESS_MESSAGES: ChatMessage[] = [
  {
    id: 'na-1',
    role: 'bot',
    text: 'Perfect — here is the formula for a new DCM account:',
    delayMs: 0,
  },
  {
    id: 'na-2',
    role: 'bot',
    text: '1. Sign in with Microsoft SSO on this page.\n2. Fill the DCM access request form (justification + optional landing zones).\n3. Submit — admins get a Teams notification.\n4. Wait for email approval, then sign in again.',
    delayMs: 900,
  },
  {
    id: 'na-3',
    role: 'bot',
    text: 'Ready? I can open the sign-in flow and the access form for you.',
    delayMs: 1100,
  },
];

export const NEED_LZ_MESSAGES: ChatMessage[] = [
  {
    id: 'lz-1',
    role: 'bot',
    text: 'Already in DCM — nice! For a new landing zone:',
    delayMs: 0,
  },
  {
    id: 'lz-2',
    role: 'bot',
    text: '1. Sign in → open My Landing Zones.\n2. Click Request access on the zone you need.\n3. Submit — same Teams notification & approval flow.',
    delayMs: 900,
  },
  {
    id: 'lz-3',
    role: 'bot',
    text: 'Sign in first — then head to My Landing Zones from the sidebar.',
    delayMs: 1100,
  },
];

export const EXPLORING_MESSAGES: ChatMessage[] = [
  {
    id: 'ex-1',
    role: 'bot',
    text: 'No problem! Browse the features on this page, or sign in if you already have access.',
    delayMs: 0,
  },
  {
    id: 'ex-2',
    role: 'bot',
    text: 'Changed your mind? Tap below anytime — I stay here.',
    delayMs: 800,
  },
];

export function choiceLabel(id: ChatChoiceId): string {
  return ROOT_CHOICES.find((c) => c.id === id)?.label ?? 'Start over';
}

export function messagesForPhase(phase: ChatPhase): ChatMessage[] {
  switch (phase) {
    case 'no-access':
      return NO_ACCESS_MESSAGES;
    case 'need-lz':
      return NEED_LZ_MESSAGES;
    case 'exploring':
      return EXPLORING_MESSAGES;
    default:
      return [];
  }
}
