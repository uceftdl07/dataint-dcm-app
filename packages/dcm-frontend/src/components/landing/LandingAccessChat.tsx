import { ArrowRight, MessageCircle, Minus } from 'lucide-react';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { LandingInteractiveCat } from './LandingInteractiveCat';
import {
  ChatChoice,
  ChatChoiceId,
  ChatMessage,
  ChatPhase,
  GREETING_MESSAGES,
  ROOT_CHOICES,
  messagesForPhase,
} from './landing-chat-flow';

interface LandingAccessChatProps {
  onRequestAccess: () => void;
}

const TYPING_MS = 520;

function useStaggeredMessages(
  queue: ChatMessage[],
  active: boolean,
  resetKey: string,
  onDone?: () => void,
) {
  const [visible, setVisible] = useState<ChatMessage[]>([]);
  const [typing, setTyping] = useState(false);
  const timers = useRef<number[]>([]);

  const clearTimers = useCallback(() => {
    timers.current.forEach((id) => window.clearTimeout(id));
    timers.current = [];
  }, []);

  useEffect(() => {
    clearTimers();
    if (!active || queue.length === 0) {
      setVisible([]);
      setTyping(false);
      return;
    }

    setVisible([]);
    setTyping(true);

    let elapsed = TYPING_MS;
    queue.forEach((msg, index) => {
      const showAt = (msg.delayMs ?? 0) + (index === 0 ? 0 : elapsed);
      const showId = window.setTimeout(() => {
        setTyping(false);
        setVisible((prev) => [...prev, msg]);
        if (index < queue.length - 1) {
          setTyping(true);
        } else {
          onDone?.();
        }
      }, showAt);
      timers.current.push(showId);
      elapsed += (msg.delayMs ?? 600) + TYPING_MS;
    });

    return clearTimers;
    // resetKey forces replay when conversation restarts
    // eslint-disable-next-line react-hooks/exhaustive-deps -- queue content tied to resetKey
  }, [active, resetKey, clearTimers, onDone]);

  return { visible, typing };
}

export const LandingAccessChat: React.FC<LandingAccessChatProps> = ({
  onRequestAccess,
}) => {
  const [open, setOpen] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [clicked, setClicked] = useState(false);
  const [phase, setPhase] = useState<ChatPhase>('greeting');
  const [selectedChoice, setSelectedChoice] = useState<ChatChoiceId | null>(null);
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [choicesVisible, setChoicesVisible] = useState(false);
  const [teaserVisible, setTeaserVisible] = useState(false);
  const [flowKey, setFlowKey] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  const greeting = useStaggeredMessages(
    GREETING_MESSAGES,
    open && phase === 'greeting',
    `greet-${flowKey}`,
    () => setChoicesVisible(true),
  );

  const branchQueue = messagesForPhase(phase);
  const branch = useStaggeredMessages(
    branchQueue,
    open && selectedChoice !== null && phase !== 'greeting' && phase !== 'done',
    `branch-${selectedChoice}-${flowKey}`,
    () => setPhase('done'),
  );

  const activeStream =
    phase === 'greeting'
      ? { messages: greeting.visible, typing: greeting.typing }
      : { messages: [...history, ...branch.visible], typing: branch.typing };

  useEffect(() => {
    const id = window.setTimeout(() => setTeaserVisible(true), 2800);
    return () => window.clearTimeout(id);
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [activeStream.messages, activeStream.typing, open]);

  const handleOpen = () => {
    setClicked(true);
    window.setTimeout(() => setClicked(false), 420);
    setOpen(true);
    setTeaserVisible(false);
  };

  const handleChoice = (choice: ChatChoice) => {
    setChoicesVisible(false);
    setSelectedChoice(choice.id);
    const userMsg: ChatMessage = {
      id: `user-${choice.id}`,
      role: 'user',
      text: choice.label,
    };
    setHistory((prev) => [...prev, ...greeting.visible, userMsg]);
    setPhase(choice.id);
  };

  const handleRestart = () => {
    setPhase('greeting');
    setSelectedChoice(null);
    setHistory([]);
    setChoicesVisible(false);
    setFlowKey((k) => k + 1);
  };

  const showRequestCta = phase === 'done' && selectedChoice === 'no-access';
  const showLzCta = phase === 'done' && selectedChoice === 'need-lz';

  return (
    <div className="landing-chat-root fixed bottom-4 right-4 z-[55] flex flex-col items-end gap-2 sm:bottom-6 sm:right-6">
      {!open && teaserVisible && (
        <button
          type="button"
          onClick={handleOpen}
          className="landing-chat-teaser pointer-events-auto max-w-[13rem] rounded-2xl border border-[#0055A4]/15 bg-white/95 px-3.5 py-2.5 text-left shadow-lg backdrop-blur-md transition hover:scale-[1.02]"
        >
          <p className="text-[11px] font-black leading-snug text-[#0055A4]">
            Need DCM access?
          </p>
          <p className="mt-0.5 text-[10px] font-medium text-slate-600">
            Chat with DataIQ — I&apos;ll guide you
          </p>
        </button>
      )}

      {open && (
        <div
          className="landing-chat-panel flex w-[min(100vw-2rem,22rem)] flex-col overflow-hidden rounded-[1.35rem] border border-white/80 bg-white/98 shadow-2xl"
          role="dialog"
          aria-label="DCM access assistant"
        >
          <div className="landing-chat-header flex items-center gap-3 border-b border-slate-100 px-4 py-3">
            <div
              className="landing-chat-avatar shrink-0"
              onMouseEnter={() => setHovered(true)}
              onMouseLeave={() => setHovered(false)}
            >
              <LandingInteractiveCat hovered={hovered} clicked={false} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-black text-slate-900">DataIQ</p>
              <p className="flex items-center gap-1.5 text-[10px] font-semibold text-emerald-600">
                <span className="landing-chat-online-dot size-1.5 rounded-full bg-emerald-500" />
                Online · DCM access guide
              </p>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
              aria-label="Minimize chat"
            >
              <Minus size={16} />
            </button>
          </div>

          <div
            ref={scrollRef}
            className="landing-chat-messages flex max-h-[min(50vh,20rem)] flex-col gap-2.5 overflow-y-auto px-3 py-4"
          >
            {activeStream.messages.map((msg) => (
              <div
                key={msg.id}
                className={`landing-chat-bubble landing-chat-bubble--${msg.role}`}
              >
                <p className="whitespace-pre-line text-[13px] leading-relaxed">{msg.text}</p>
              </div>
            ))}

            {activeStream.typing && (
              <div className="landing-chat-bubble landing-chat-bubble--bot landing-chat-typing">
                <span />
                <span />
                <span />
              </div>
            )}
          </div>

          <div className="border-t border-slate-100 px-3 py-3">
            {choicesVisible && phase === 'greeting' && !activeStream.typing && (
              <div className="flex flex-col gap-1.5">
                {ROOT_CHOICES.map((choice) => (
                  <button
                    key={choice.id}
                    type="button"
                    onClick={() => handleChoice(choice)}
                    className="landing-chat-choice rounded-xl border border-[#0055A4]/15 bg-blue-50/60 px-3 py-2.5 text-left text-[12px] font-semibold text-[#0055A4] transition hover:border-[#0055A4]/35 hover:bg-blue-50"
                  >
                    {choice.label}
                  </button>
                ))}
              </div>
            )}

            {phase === 'done' && !activeStream.typing && (
              <div className="flex flex-col gap-2">
                {showRequestCta && (
                  <button
                    type="button"
                    onClick={onRequestAccess}
                    className="group flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-[#0055A4] to-[#00AEEF] px-3 py-3 text-[11px] font-black uppercase tracking-[0.12em] text-white shadow-md transition hover:scale-[1.01] active:scale-[0.99]"
                  >
                    Sign in & open access form
                    <ArrowRight size={14} className="transition group-hover:translate-x-0.5" />
                  </button>
                )}
                {showLzCta && (
                  <button
                    type="button"
                    onClick={onRequestAccess}
                    className="group flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-[#0055A4] to-[#00AEEF] px-3 py-3 text-[11px] font-black uppercase tracking-[0.12em] text-white shadow-md transition hover:scale-[1.01] active:scale-[0.99]"
                  >
                    Sign in to DCM
                    <ArrowRight size={14} className="transition group-hover:translate-x-0.5" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleRestart}
                  className="rounded-xl py-2 text-[10px] font-bold uppercase tracking-[0.1em] text-slate-500 transition hover:bg-slate-50"
                >
                  Ask something else
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {!open && (
        <button
          type="button"
          onClick={handleOpen}
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          className="landing-chat-fab group relative flex size-[4.25rem] items-center justify-center rounded-full border-0 bg-gradient-to-br from-[#0055A4] to-[#00AEEF] p-0 shadow-xl outline-none transition hover:scale-105 focus-visible:ring-2 focus-visible:ring-[#0055A4] focus-visible:ring-offset-2"
          aria-label="Open DCM access chat"
        >
          <span className="landing-chat-fab-ping absolute inset-0 rounded-full" />
          <div className="scale-[0.72]">
            <LandingInteractiveCat hovered={hovered} clicked={clicked} />
          </div>
          <span className="absolute -right-0.5 -top-0.5 flex size-5 items-center justify-center rounded-full bg-white text-[#0055A4] shadow-md">
            <MessageCircle size={11} strokeWidth={2.5} />
          </span>
        </button>
      )}
    </div>
  );
};
