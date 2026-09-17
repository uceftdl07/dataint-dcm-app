import React, { useState, useEffect, useRef } from 'react';
import {
  Send, CheckCircle, Loader2,
  ChevronRight, RotateCcw, Zap, Database, Activity, ShieldCheck, Cloud,
  MessageCircle, X, Sparkles
} from 'lucide-react';
import { postChat } from '../api/dcmApiClient';
import { Card, CardContent } from '../components/ui/card';
import { Textarea } from '../components/ui/input';
import { DataIQAvatar } from '../components/DataIQAvatar';
import { DATAIQ_BRAND } from '../config/dataiq';
import type { ChatMessage as ApiChatMessage } from '../types/api';

// ─────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  sourceLabel?: string;
  sources?: string[];
}

interface SuggestedQuestion {
  id: string;
  emoji: string;
  shortLabel: string;
  fullQuestion: string;
  thinkingSteps: string[];
}

const DEFAULT_THINKING_STEPS = [
  'Analyzing your question...',
  'Loading DCM data...',
  'Preparing the summary...',
];

// ─────────────────────────────────────────────
// SUGGESTED QUESTIONS
// ─────────────────────────────────────────────
const SUGGESTED_QUESTIONS: SuggestedQuestion[] = [
  {
    id: 'multi-cloud-costs',
    emoji: '💰',
    shortLabel: 'Multi-cloud costs',
    fullQuestion: 'Compare my Azure and AWS costs for this month',
    thinkingSteps: [
      'Checking cost summary...',
      'Comparing services by cloud...',
      'Preparing the FinOps summary...',
    ],
  },
  {
    id: 'pipeline-health',
    emoji: '🏭',
    shortLabel: 'Pipeline health',
    fullQuestion: 'Which pipelines are failing on Azure and AWS?',
    thinkingSteps: [
      'Checking failed pipeline runs...',
      'Ranking recent failures...',
      'Summarizing main errors...',
    ],
  },
  {
    id: 'security-audit',
    emoji: '🛡️',
    shortLabel: 'AI security audit',
    fullQuestion: 'Analyze the security of my Azure and AWS databases',
    thinkingSteps: [
      'Checking security alerts...',
      'Filtering active alerts...',
      'Summarizing main risks...',
    ],
  },
  {
    id: 'governance-score',
    emoji: '✅',
    shortLabel: 'Governance',
    fullQuestion: 'What is the compliance score for landing zones?',
    thinkingSteps: [
      'Checking compliance score...',
      'Reviewing standard checks...',
      'Summarizing non-compliant checks...',
    ],
  },
  {
    id: 'data-product-usage',
    emoji: '📦',
    shortLabel: 'Usage Data Products',
    fullQuestion: 'Which data products are consumed the most?',
    thinkingSteps: [
      'Checking data product usage...',
      'Ranking top consumers...',
      'Summarizing main usage patterns...',
    ],
  },
  {
    id: 'compute-health',
    emoji: '⚙️',
    shortLabel: 'Clusters & Compute',
    fullQuestion: 'What is the state of clusters and compute resources?',
    thinkingSteps: [
      'Checking compute resources...',
      'Analyzing compute states...',
      'Summarizing active resources...',
    ],
  },
  {
    id: 'database-health',
    emoji: '🗄️',
    shortLabel: 'Databases',
    fullQuestion: 'Which databases are unavailable or need monitoring?',
    thinkingSteps: [
      'Checking database inventory...',
      'Checking availability and capacity...',
      'Summarizing databases to monitor...',
    ],
  },
  {
    id: 'platform-overview',
    emoji: '📊',
    shortLabel: 'Global view',
    fullQuestion: 'Give me a global overview of the DCM platform',
    thinkingSteps: [
      'Checking platform overview...',
      'Aggregating key KPIs...',
      'Preparing the global summary...',
    ],
  },
];

const THINKING_STEP_DELAY_MS = 400;
const THINKING_STEP_JITTER_MS = 150;
const TYPING_EFFECT_MAX_CHARS = 300;
const TYPING_EFFECT_INTERVAL_MS = 8;

const waitForThinkingStep = (): Promise<void> =>
  new Promise(resolve => setTimeout(resolve, THINKING_STEP_DELAY_MS + Math.random() * THINKING_STEP_JITTER_MS));

const toApiMessages = (messages: Message[]): ApiChatMessage[] =>
  messages.slice(-10).map(message => ({
    role: message.role,
    content: message.content,
  }));

// ─────────────────────────────────────────────
// RESPONSE RENDERER
// ─────────────────────────────────────────────
const ResponseLine: React.FC<{ line: string }> = ({ line }) => {
  if (line.startsWith('━')) {
    return <div className="my-3 border-t border-border" />;
  }
  if (line.trim() === '') return <div className="h-2" />;

  const isBold = line.includes('**');
  const cleaned = line.replace(/\*\*/g, '');

  let colorClass = 'text-card-foreground';
  if (line.includes('✅')) colorClass = 'text-success';
  else if (line.includes('❌')) colorClass = 'text-danger';
  else if (line.includes('⚠️')) colorClass = 'text-warning';
  else if (line.includes('💡')) colorClass = 'text-info';
  else if (line.includes('🔴')) colorClass = 'text-danger';
  else if (line.includes('📊') || line.includes('📈') || line.includes('💰'))
    colorClass = 'text-info';
  else if (line.startsWith('  1.') || line.startsWith('  2.') || line.startsWith('  3.'))
    colorClass = 'text-foreground';

  return (
    <div className={`${colorClass} leading-relaxed font-mono text-sm ${isBold ? 'font-bold' : ''}`}>
      {isBold
        ? cleaned
        : line.replace(/\*\*/g, '').split(/(\b\d[\d\s€%,.]+[€%]?\b)/g).map((part, i) =>
            /\d/.test(part) && (part.includes('€') || part.includes('%'))
              ? <span key={i} className="font-bold text-info">{part}</span>
              : <span key={i}>{part}</span>
          )
      }
    </div>
  );
};

const FormattedResponse: React.FC<{ text: string; isTyping: boolean }> = ({ text, isTyping }) => (
  <div className="space-y-1 text-card-foreground">
    {text.split('\n').map((line, i) => (
      <ResponseLine key={i} line={line} />
    ))}
    {isTyping && (
      <span className="ml-1 inline-block h-4 w-2 animate-pulse bg-primary align-middle" />
    )}
  </div>
);

// ─────────────────────────────────────────────
// THINKING ANIMATION
// ─────────────────────────────────────────────
const ThinkingIndicator: React.FC<{ steps: string[]; currentStep: number }> = ({ steps, currentStep }) => (
  <div className="flex justify-start">
    <div className="max-w-2xl w-full">
      <div className="flex items-center space-x-3 mb-2">
        <DataIQAvatar size="xs" />
        <span className="text-[10px] font-semibold uppercase tracking-widest text-info">{DATAIQ_BRAND.engineLabel}</span>
      </div>
      <Card className="ml-11 rounded-tl-sm bg-card/90">
        <CardContent className="space-y-3">
        {steps.map((step, i) => (
          <div key={i} className="flex items-center space-x-3">
            {i < currentStep ? (
              <CheckCircle className="h-4 w-4 flex-shrink-0 text-success" />
            ) : i === currentStep ? (
              <Loader2 className="h-4 w-4 flex-shrink-0 animate-spin text-info" />
            ) : (
              <div className="h-4 w-4 flex-shrink-0 rounded-full border border-border" />
            )}
            <span className={`text-xs font-mono transition-all duration-300 ${
              i < currentStep ? 'text-success/70 line-through' :
              i === currentStep ? 'font-bold text-info' : 'text-muted-foreground'
            }`}>
              {step}
            </span>
          </div>
        ))}
        </CardContent>
      </Card>
    </div>
  </div>
);

const GenieNotice: React.FC<{ compact?: boolean }> = ({ compact = false }) => (
  <div className={`flex gap-3 rounded-2xl border border-primary/20 bg-primary/5 text-left shadow-sm ${compact ? 'px-4 py-3' : 'px-5 py-4'}`}>
    <div className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
      <Zap size={16} />
    </div>
    <div className="space-y-1">
      <p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">Databricks Genie</p>
      <p className={`${compact ? 'text-sm' : 'text-base'} font-medium leading-relaxed text-foreground`}>
        Ask questions in natural language. Responses are powered by Databricks Genie on your DCM data.
      </p>
    </div>
  </div>
);

// ─────────────────────────────────────────────
// MAIN PAGE COMPONENT
// ─────────────────────────────────────────────
const TalkToYourData: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [thinkingStep, setThinkingStep] = useState(0);
  const [currentThinkingSteps, setCurrentThinkingSteps] = useState<string[]>([]);
  const [typingText, setTypingText] = useState('');
  const [isTypingEffect, setIsTypingEffect] = useState(false);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [lastFailedQuery, setLastFailedQuery] = useState<string | null>(null);
  const [lastFailedThinkingSteps, setLastFailedThinkingSteps] = useState<string[]>(DEFAULT_THINKING_STEPS);
  const chatAreaRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const typingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const scrollToBottom = () => {
    if (chatAreaRef.current) {
      chatAreaRef.current.scrollTop = chatAreaRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, typingText, isThinking]);

  useEffect(() => {
    if (!isChatOpen) return;
    const focusTimer = setTimeout(() => inputRef.current?.focus(), 150);
    return () => clearTimeout(focusTimer);
  }, [isChatOpen]);

  const startTypingEffect = (text: string) => {
    if (typingIntervalRef.current) clearInterval(typingIntervalRef.current);
    if (text.length > TYPING_EFFECT_MAX_CHARS) {
      setTypingText(text);
      setIsTypingEffect(false);
      return;
    }
    setTypingText('');
    setIsTypingEffect(true);
    let i = 0;
    typingIntervalRef.current = setInterval(() => {
      if (i < text.length) {
        setTypingText(text.slice(0, i + 1));
        i++;
      } else {
        clearInterval(typingIntervalRef.current!);
        setIsTypingEffect(false);
      }
    }, TYPING_EFFECT_INTERVAL_MS);
  };

  const handleSend = async (query: string, thinkingSteps: string[] = DEFAULT_THINKING_STEPS) => {
    if (!query.trim() || isThinking || isTypingEffect) return;

    setIsChatOpen(true);

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: query,
      timestamp: new Date(),
    };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInputValue('');

    setIsThinking(true);
    setThinkingStep(0);
    setCurrentThinkingSteps(thinkingSteps);

    const answerPromise = postChat({ messages: toApiMessages(nextMessages) });

    let thinkingCancelled = false;
    const thinkingAnimation = (async () => {
      for (let step = 0; step < thinkingSteps.length; step++) {
        if (thinkingCancelled) return;
        await waitForThinkingStep();
        if (thinkingCancelled) return;
        setThinkingStep(step + 1);
      }
    })();

    try {
      const answer = await answerPromise;
      thinkingCancelled = true;
      setLastFailedQuery(null);

      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: answer.text,
        timestamp: new Date(),
        sourceLabel: answer.source_label,
        sources: answer.sources,
      };
      setMessages(prev => [...prev, assistantMsg]);
      startTypingEffect(answer.text);
    } catch {
      thinkingCancelled = true;
      const fallbackText = 'I cannot reach the chat API right now. Please retry in a moment.';
      setLastFailedQuery(query);
      setLastFailedThinkingSteps(thinkingSteps);
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: fallbackText,
        timestamp: new Date(),
        sourceLabel: 'Error API',
        sources: ['/api/v1/chat'],
      };
      setMessages(prev => [...prev, errorMsg]);
      startTypingEffect(fallbackText);
    } finally {
      thinkingCancelled = true;
      setIsThinking(false);
      void thinkingAnimation;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend(inputValue);
    }
  };

  const handleReset = () => {
    if (typingIntervalRef.current) clearInterval(typingIntervalRef.current);
    setMessages([]);
    setInputValue('');
    setIsThinking(false);
    setTypingText('');
    setIsTypingEffect(false);
    setLastFailedQuery(null);
  };

  const isIdle = messages.length === 0 && !isThinking;
  const lastAssistantIndex = messages.map(m => m.role).lastIndexOf('assistant');

  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-background text-foreground">
      
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute left-1/4 top-0 h-[600px] w-[600px] rounded-full bg-primary/5 blur-[120px]" />
        <div className="absolute bottom-0 right-1/4 h-[500px] w-[500px] rounded-full bg-purple/5 blur-[120px]" />
      </div>

      {/* ── Landing ── */}
      {!isChatOpen && (
        <div className="relative z-10 flex flex-1 items-start justify-center overflow-y-auto px-4 py-6 custom-scrollbar sm:px-6 lg:px-8">
        <div className="mx-auto grid w-full max-w-5xl items-center gap-8 2xl:max-w-6xl 2xl:grid-cols-[1.05fr_0.95fr]">
          <div className="space-y-7">
            <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card/80 px-4 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary shadow-sm backdrop-blur">
              <Sparkles size={14} />
              {DATAIQ_BRAND.tagline}
            </div>

            <div className="space-y-5">
              <h1 className="max-w-3xl text-4xl font-semibold tracking-[-0.06em] text-foreground md:text-6xl">
                Talk to your <span className="text-primary">Data</span>
              </h1>
              <p className="max-w-2xl text-base font-medium leading-relaxed text-muted-foreground md:text-lg">
                Ask operational questions across costs, pipelines, alerts, governance and data platforms.
              </p>
              <div className="max-w-2xl">
                <GenieNotice />
              </div>
            </div>

            <div className="flex flex-wrap gap-3">
              {[
                { icon: <Database size={14}/>, label: 'Azure Hub' },
                { icon: <Cloud size={14}/>, label: 'AWS Node' },
                { icon: <Activity size={14}/>, label: 'Pipelines' },
                { icon: <ShieldCheck size={14}/>, label: 'Compliance' },
              ].map((cap, i) => (
                <div key={i} className="flex items-center gap-2 rounded-full border border-border bg-muted/60 px-4 py-2 text-xs font-medium text-primary">
                  {cap.icon}
                  {cap.label}
                </div>
              ))}
            </div>

            <button
              onClick={() => setIsChatOpen(true)}
              className="inline-flex items-center gap-3 rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground shadow-xl shadow-primary/20 transition-all hover:-translate-y-0.5 hover:brightness-105 active:scale-95"
            >
              <MessageCircle size={18} />
              Open chatbot
            </button>
          </div>

          <div className="relative mx-auto flex w-full max-w-sm justify-center 2xl:max-w-md 2xl:justify-end">
            <div className="pointer-events-none absolute left-1/2 top-1/2 size-48 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/25 blur-[72px] sm:size-56" />
            <button
              type="button"
              onClick={() => setIsChatOpen(true)}
              className="group relative flex flex-col items-center gap-4 transition-all hover:-translate-y-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label={DATAIQ_BRAND.openLabel}
            >
              <DataIQAvatar
                size="hero"
                ring
                className="shadow-2xl shadow-primary/35 transition-transform duration-300 group-hover:scale-105"
              />
              <div className="absolute -right-1 top-2 flex items-center gap-2 rounded-full border border-border bg-background/95 px-3 py-1.5 text-xs font-semibold text-success shadow-lg backdrop-blur sm:-right-3 sm:top-4">
                <span className="h-2 w-2 animate-pulse rounded-full bg-success" />
                AI ready
              </div>
              <div className="flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground shadow-xl shadow-primary/25">
                <MessageCircle size={14} />
                Click to chat
              </div>
            </button>
          </div>
        </div>
        </div>
      )}

      {/* ── Chatbot Panel ── */}
      {isChatOpen && (
        <div className="relative z-10 mx-auto my-4 flex min-h-0 w-[calc(100%-2rem)] max-w-6xl flex-1 flex-col overflow-hidden rounded-[28px] border border-border/70 bg-[color:var(--card-background)] text-foreground shadow-xl backdrop-blur-3xl animate-in fade-in zoom-in-95 duration-300 md:my-6 md:w-[calc(100%-3rem)]">
          <div className="flex items-center justify-between border-b border-border/60 bg-background/45 px-5 py-4 md:px-7">
            <div className="flex items-center gap-3">
              <DataIQAvatar size="md" ring />
              <div>
                <h2 className="text-lg font-semibold tracking-[-0.03em] text-foreground">{DATAIQ_BRAND.name}</h2>
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  <p className="text-xs font-medium text-muted-foreground">{DATAIQ_BRAND.iqHint}</p>
                  <span className="text-muted-foreground/50">·</span>
                  <div className="flex items-center gap-1.5">
                    <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-success" />
                    <p className="text-xs font-medium text-muted-foreground">Powered by Databricks Genie</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-1">
              {messages.length > 0 && (
                <button onClick={handleReset} className="rounded-full border border-transparent p-2 text-muted-foreground transition-all hover:border-border hover:bg-accent hover:text-accent-foreground" aria-label="Reset conversation">
                  <RotateCcw size={16} />
                </button>
              )}
              <button onClick={() => setIsChatOpen(false)} className="rounded-full border border-transparent p-2 text-muted-foreground transition-all hover:border-border hover:bg-accent hover:text-accent-foreground" aria-label="Close the chatbot">
                <X size={17} />
              </button>
            </div>
          </div>

          <div ref={chatAreaRef} className="flex-1 overflow-y-auto px-5 py-7 custom-scrollbar md:px-8 lg:px-10">
            <div className="mx-auto max-w-5xl space-y-8">
              {isIdle && (
                <div className="flex flex-col items-center py-10 text-center space-y-6 animate-in fade-in zoom-in duration-500 md:py-16">
                  <div className="relative">
                    <div className="pointer-events-none absolute inset-0 rounded-full bg-primary/20 blur-[48px]" />
                    <DataIQAvatar
                      size="xl"
                      ring
                      className="relative shadow-2xl shadow-primary/30 transition-transform duration-300 hover:rotate-3"
                    />
                    <div className="absolute -right-2 -top-2 flex size-10 animate-bounce items-center justify-center rounded-full bg-warning shadow-xl sm:-right-3 sm:-top-3 sm:size-11">
                      <Zap size={18} className="fill-current text-warning-foreground" />
                    </div>
                  </div>

                  <div className="space-y-3">
                    <h3 className="text-4xl font-semibold tracking-[-0.05em] text-foreground">
                      Hello, I am <span className="text-primary">{DATAIQ_BRAND.name}</span>
                    </h3>
                    <p className="mx-auto max-w-xl text-base font-semibold leading-relaxed text-foreground">
                      Ask me a question about costs, pipelines, security alerts, governance, data products, clusters, or databases.
                    </p>
                    <div className="mx-auto max-w-xl">
                      <GenieNotice compact />
                    </div>
                  </div>
                </div>
              )}

              {messages.map((msg, index) => (
                <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-in slide-in-from-bottom-4 duration-500`}>
                  <div className="w-full max-w-4xl">
                    {msg.role === 'user' ? (
                      <div className="flex justify-end">
                        <div className="max-w-2xl rounded-[24px] rounded-tr-sm bg-primary px-6 py-4 text-sm font-semibold text-primary-foreground shadow-xl shadow-primary/20">
                          {msg.content}
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-start gap-3">
                        <DataIQAvatar size="sm" className="shadow-md" />
                        <div className="min-w-0 flex-1 space-y-2">
                          <div className="flex items-center gap-3">
                            <span className="text-xs font-semibold text-info">{DATAIQ_BRAND.engineLabel}</span>
                            <span className="text-xs font-medium text-muted-foreground">
                              {msg.timestamp.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
                            </span>
                          </div>
                          <Card className="rounded-tl-sm bg-[color:var(--card-background)] text-card-foreground backdrop-blur-2xl">
                            <CardContent className="px-4 py-4">
                            {index === lastAssistantIndex && isTypingEffect ? (
                              <FormattedResponse text={typingText} isTyping={true} />
                            ) : (
                              <FormattedResponse text={msg.content} isTyping={false} />
                            )}
                            {msg.sourceLabel && (
                              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3">
                                <span className="rounded-full border border-info-border bg-info-subtle px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-info">
                                  {msg.sourceLabel}
                                </span>
                                {msg.sources?.map(source => (
                                  <span key={source} className="rounded-full bg-muted px-2.5 py-1 text-[10px] font-medium text-muted-foreground">
                                    {source}
                                  </span>
                                ))}
                              </div>
                            )}
                            </CardContent>
                          </Card>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {isThinking && (
                <ThinkingIndicator steps={currentThinkingSteps} currentStep={thinkingStep} />
              )}
            </div>
          </div>

          <div className="border-t border-border/60 bg-background/45 p-5 md:px-8">
            <div className="mx-auto max-w-5xl">
            {isIdle && (
              <div className="mb-5 grid grid-cols-1 gap-3 lg:grid-cols-3">
                {SUGGESTED_QUESTIONS.map(q => (
                  <Card
                    key={q.id}
                    onClick={() => handleSend(q.fullQuestion, q.thinkingSteps)}
                    onKeyDown={(event) => {
                      if (event.key !== 'Enter' && event.key !== ' ') return;
                      event.preventDefault();
                      handleSend(q.fullQuestion, q.thinkingSteps);
                    }}
                    role="button"
                    tabIndex={0}
                    interactive
                    className="group bg-[color:var(--card-background)] text-left hover:bg-accent/35"
                  >
                    <CardContent className="space-y-2 px-4 py-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex min-w-0 items-center gap-3">
                          <span className="text-xl">{q.emoji}</span>
                          <div className="min-w-0">
                            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-foreground">{q.shortLabel}</p>
                            <p className="truncate text-xs leading-relaxed text-muted-foreground transition-colors group-hover:text-foreground">{q.fullQuestion}</p>
                          </div>
                        </div>
                        <ChevronRight size={14} className="flex-shrink-0 text-muted-foreground transition-colors group-hover:text-primary" />
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}

            <div className="flex items-end gap-3">
              <div className="relative flex-1">
                <Textarea
                  ref={inputRef}
                  value={inputValue}
                  onChange={e => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask about your Azure and AWS ecosystems..."
                  rows={1}
                  disabled={isThinking || isTypingEffect}
                  className="custom-scrollbar max-h-[140px] min-h-[52px] resize-none bg-background px-4 py-3 focus-visible:border-primary/50"
                  onInput={e => {
                    const t = e.target as HTMLTextAreaElement;
                    t.style.height = 'auto';
                    t.style.height = t.scrollHeight + 'px';
                  }}
                />
              </div>
              <button
                onClick={() => handleSend(inputValue)}
                disabled={!inputValue.trim() || isThinking || isTypingEffect}
                className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-[18px] bg-primary text-primary-foreground shadow-xl shadow-primary/20 transition-all hover:scale-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
                aria-label="Send message"
              >
                {isThinking ? <Loader2 size={22} className="animate-spin" /> : <Send size={22} />}
              </button>
            </div>

            <p className="mt-3 text-center text-[11px] font-medium text-muted-foreground">
              Powered by Databricks Genie
            </p>
            {lastFailedQuery && !isThinking && (
              <div className="mt-3 flex justify-center">
                <button
                  type="button"
                  onClick={() => handleSend(lastFailedQuery, lastFailedThinkingSteps)}
                  className="rounded-full border border-border bg-muted px-3 py-1.5 text-xs font-semibold text-foreground transition hover:bg-accent"
                >
                  Retry last message
                </button>
              </div>
            )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TalkToYourData;
