import { useState, useEffect, useRef } from 'react';
import { X, Send, ExternalLink, ThumbsUp, ThumbsDown } from 'lucide-react';

// Support-agent avatar (head + shoulders with a headset) — inherits currentColor.
const AssistantAvatar = ({ className }: { className?: string }) => (
  <svg viewBox="0 0 28 28" className={className} fill="none" aria-hidden="true">
    <path d="M8.2 12.6a5.8 5.8 0 0 1 11.6 0" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    <rect x="6.6" y="11.3" width="2.6" height="3.4" rx="1.3" fill="currentColor" />
    <rect x="18.8" y="11.3" width="2.6" height="3.4" rx="1.3" fill="currentColor" />
    <path d="M19.9 14.7v.8a1.6 1.6 0 0 1-1.6 1.6h-2.3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="14" cy="12.4" r="3.7" fill="currentColor" />
    <path d="M20.6 24c0-3.5-3-5.7-6.6-5.7S7.4 20.5 7.4 24z" fill="currentColor" />
  </svg>
);

// Metzler wordmark logo (red/black), inlined so it needs no asset path.
const METZLER_LOGO =
  'data:image/png;base64,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';
import { chatAPI, suggestionsAPI } from '../services/api';
import { ChatResponse, ProductCard as ProductType } from '../types';
import { safeUrl, formatPrice } from '../utils/format';

interface Msg {
  role: 'user' | 'assistant';
  text: string;
  products?: ProductType[];
  refine?: string[];
  followUp?: string;
  interactionId?: number;
  feedback?: 'up' | 'down';
}

interface Props {
  // Current storefront category, used to fetch context-aware suggestions.
  category?: string | null;
}

export default function ChatWidget({ category }: Props) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Refetch suggestions whenever the category context changes.
  useEffect(() => {
    suggestionsAPI
      .get(category || undefined)
      .then(setSuggestions)
      .catch((err) => console.error('suggestions load failed', err));
  }, [category]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  const send = async (text: string, isRefinement = false) => {
    const q = text.trim();
    if (!q || loading) return;
    // Prior turns (before this message) are the conversation memory sent to
    // the backend, so follow-ups like "and with LED?" are understood in context.
    const history = messages.slice(-8).map((m) => ({ role: m.role, content: m.text }));
    setMessages((m) => [...m, { role: 'user', text: q }]);
    setInput('');
    setLoading(true);
    try {
      const res: ChatResponse = await chatAPI.sendMessage(q, history, isRefinement);
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          text: res.answer,
          products: res.products,
          refine: res.refine_suggestions,
          followUp: res.follow_up_question || undefined,
          interactionId: res.interaction_id,
        },
      ]);
    } catch (err) {
      console.error(err);
      setMessages((m) => [
        ...m,
        { role: 'assistant', text: 'Sorry, something went wrong. Please try again.' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant');
  const activeRefine = !loading ? lastAssistant?.refine ?? [] : [];

  // Attach thumbs feedback to a logged answer (tap again to clear).
  const rate = async (idx: number, rating: 'up' | 'down') => {
    const msg = messages[idx];
    if (!msg?.interactionId) return;
    const next = msg.feedback === rating ? 'none' : rating;
    setMessages((m) =>
      m.map((mm, i) => (i === idx ? { ...mm, feedback: next === 'none' ? undefined : next } : mm))
    );
    try {
      await chatAPI.sendFeedback(msg.interactionId, next);
    } catch (err) {
      console.error('feedback failed', err);
    }
  };

  return (
    <>
      <style>{`
        .pc-input::-webkit-search-cancel-button{ -webkit-appearance:none; appearance:none; width:16px; height:16px; margin-left:8px; cursor:pointer; opacity:.85; transition:opacity .15s; background:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23A1A1A1' stroke-width='2.2' stroke-linecap='round'><line x1='6' y1='6' x2='18' y2='18'/><line x1='6' y1='18' x2='18' y2='6'/></svg>") center / contain no-repeat; }
        .pc-input::-webkit-search-cancel-button:hover{ opacity:1; }
      `}</style>
      {/* Floating launcher */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          aria-label="Ask the assistant"
          title="Ask the assistant"
          className="fixed bottom-5 right-5 z-50 flex items-center justify-center w-14 h-14 rounded-full bg-[#015253]/80 backdrop-blur-md hover:bg-[#02696a]/[0.88] text-white shadow-[0_4px_12px_-3px_rgba(1,82,83,0.32)] hover:shadow-[0_8px_20px_-6px_rgba(1,82,83,0.4)] hover:-translate-y-0.5 hover:scale-105 active:scale-95 transition-all"
        >
          <AssistantAvatar className="w-[34px] h-[34px]" />
        </button>
      )}

      {/* Panel */}
      {open && (
        <div className="fixed bottom-5 right-5 z-50 w-[calc(100vw-2.5rem)] sm:w-[358px] h-[540px] max-h-[calc(100dvh-2.5rem)] bg-white rounded-[20px] shadow-2xl border border-[#015253]/10 flex flex-col overflow-hidden">
          {/* Header */}
          <div
            className="flex items-center justify-between px-3.5 py-3 text-white shadow-[inset_0_-1px_0_rgba(255,255,255,0.1)]"
            style={{
              background:
                'radial-gradient(95% 130% at 22% -20%, rgba(255,255,255,0.14), rgba(255,255,255,0) 55%), radial-gradient(120% 150% at 20% 0%, #05867f, #015b58 42%, #013d3e)',
            }}
          >
            <div className="flex items-center gap-2.5">
              <div className="relative w-9 h-9 rounded-xl bg-white/[0.16] ring-1 ring-white/10 flex items-center justify-center">
                <AssistantAvatar className="w-[21px] h-[21px]" />
                <span className="absolute -right-0.5 -bottom-0.5 w-2.5 h-2.5 rounded-full bg-[#2fd08a] ring-2 ring-[#024e4c]" />
              </div>
              <div className="leading-tight">
                <p className="font-semibold text-sm">Product Assistant</p>
                <p className="text-[11px] text-white/70">
                  {category ? `Browsing: ${category}` : 'How can I help you find a product?'}
                </p>
              </div>
            </div>
            <button onClick={() => setOpen(false)} className="p-1.5 rounded-lg hover:bg-white/20 transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Body */}
          <div
            ref={scrollRef}
            className={`flex-1 overflow-y-auto p-3.5 space-y-3 bg-[#f5f6fa] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden ${
              messages.length === 0 ? 'flex flex-col justify-center' : ''
            }`}
          >
            {messages.length === 0 && (
              <div className="text-center">
                <img src={METZLER_LOGO} alt="Metzler" className="w-[158px] max-w-[72%] h-auto mx-auto mb-3.5 mt-0.5" />
                <p className="text-sm text-slate-600 mb-1 font-medium">
                  {category ? `Questions about ${category.toLowerCase()}` : 'Not sure where to start?'}
                </p>
                <p className="text-xs text-slate-400">Pick a question below or type your own.</p>
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
                <div className={m.role === 'user' ? 'max-w-[85%]' : 'max-w-[92%] w-full'}>
                  <div
                    className={
                      m.role === 'user'
                        ? 'bg-[linear-gradient(155deg,#02696a,#014a4b)] text-white rounded-2xl rounded-br-sm px-3.5 py-2.5 text-sm shadow-[0_2px_8px_-3px_rgba(1,82,83,0.4)]'
                        : 'bg-white border border-slate-200 rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm text-slate-700 shadow-sm'
                    }
                  >
                    {m.text}
                  </div>

                  {/* Product results */}
                  {m.products && m.products.length > 0 && (
                    <div className="mt-2 space-y-2">
                      {m.products.map((p) => (
                        <a
                          key={p.id}
                          href={safeUrl(p.url) || '#'}
                          target={safeUrl(p.url) ? '_blank' : undefined}
                          rel="noopener noreferrer"
                          className="flex gap-3 bg-white border border-slate-200 rounded-xl p-2.5 hover:border-[#7fb3b3] hover:shadow-sm transition-all group"
                        >
                          {safeUrl(p.image) && (
                            <img
                              src={safeUrl(p.image)}
                              alt={p.name}
                              className="w-14 h-14 rounded-lg object-cover bg-slate-100 flex-shrink-0"
                              onError={(e) => (e.currentTarget.style.display = 'none')}
                            />
                          )}
                          <div className="min-w-0 flex-1">
                            <p className="text-xs font-medium text-slate-900 line-clamp-2">{p.name}</p>
                            <div className="flex items-center justify-between mt-1">
                              {p.price != null && (
                                <span className="text-sm font-bold text-emerald-600">
                                  {p.has_variants ? 'ab ' : ''}{formatPrice(p.price)}
                                </span>
                              )}
                              {p.url && (
                                <span className="flex items-center gap-1 text-[11px] text-[#015253] group-hover:underline">
                                  View <ExternalLink className="w-3 h-3" />
                                </span>
                              )}
                            </div>
                          </div>
                        </a>
                      ))}
                    </div>
                  )}

                  {m.followUp && (
                    <p className="mt-2 text-xs text-[#013b3c] bg-[#e9f3f3] border border-[#d3e6e5] rounded-lg px-3 py-2">
                      {m.followUp}
                    </p>
                  )}

                  {m.role === 'assistant' && m.interactionId && (
                    <div className="flex items-center gap-1 mt-1.5 pl-0.5">
                      <button
                        onClick={() => rate(i, 'up')}
                        aria-label="Helpful"
                        title="Helpful"
                        className={`p-1 rounded-md transition-colors ${
                          m.feedback === 'up'
                            ? 'text-emerald-600 bg-emerald-50'
                            : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100'
                        }`}
                      >
                        <ThumbsUp className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => rate(i, 'down')}
                        aria-label="Not helpful"
                        title="Not helpful"
                        className={`p-1 rounded-md transition-colors ${
                          m.feedback === 'down'
                            ? 'text-rose-600 bg-rose-50'
                            : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100'
                        }`}
                      >
                        <ThumbsDown className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex items-center gap-1.5 w-fit px-3.5 py-3 bg-white border border-slate-200 rounded-2xl rounded-bl-sm shadow-sm">
                {[0, 150, 300].map((d) => (
                  <span
                    key={d}
                    className="w-1.5 h-1.5 rounded-full bg-[#8fbcb8] animate-bounce"
                    style={{ animationDelay: `${d}ms` }}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Suggestion / refine chips */}
          {(messages.length === 0 ? suggestions : activeRefine).length > 0 && (
            <div className="px-3.5 py-3 bg-white border-t border-slate-100 flex flex-wrap gap-2">
              {(messages.length === 0 ? suggestions : activeRefine).slice(0, 5).map((s) => (
                <button
                  key={s}
                  onClick={() => (messages.length === 0 ? send(s) : send(s, true))}
                  className="text-left px-3 py-2 text-xs bg-[#f2f7f6] border border-transparent rounded-full hover:bg-[#e3f0ef] hover:border-[#bcdedb] hover:text-[#015253] text-[#3d5250] transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="px-3.5 py-3 bg-white border-t border-slate-200 flex gap-2"
          >
            <input
              type="search"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your question…"
              disabled={loading}
              className="pc-input flex-1 h-11 px-3.5 text-base text-black bg-[#f5f6fa] border border-[#dadada] rounded-lg outline-none placeholder:text-[#a1a1a1] focus:border-[#015253] focus:ring-[3px] focus:ring-[rgba(1,82,83,0.1)] transition-[border-color,box-shadow]"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="w-11 h-11 flex items-center justify-center text-white rounded-lg bg-[linear-gradient(150deg,#02726e,#015253)] shadow-[0_4px_12px_-4px_rgba(1,82,83,0.5)] hover:brightness-110 active:scale-95 disabled:bg-slate-300 disabled:bg-none disabled:shadow-none transition-all"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      )}
    </>
  );
}
