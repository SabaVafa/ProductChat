import { useState, useEffect, useRef } from 'react';
import { X, Send, Loader2, Sparkles, ExternalLink, Bot, ThumbsUp, ThumbsDown } from 'lucide-react';
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
      {/* Floating launcher */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          aria-label="Ask the assistant"
          title="Ask the assistant"
          className="fixed bottom-5 right-5 z-50 flex items-center justify-center w-14 h-14 rounded-full bg-[#015253] hover:bg-[#02696a] text-white shadow-lg hover:shadow-xl hover:-translate-y-0.5 hover:scale-105 active:scale-95 transition-all"
        >
          <svg viewBox="0 0 28 28" className="w-7 h-7" fill="none">
            <path d="M6 5h16a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3h-8l-5 4v-4H6a3 3 0 0 1-3-3V8a3 3 0 0 1 3-3z" fill="#fff" />
            <path d="M14 8.1l1.05 2.75L17.8 11.9l-2.75 1.05L14 15.7l-1.05-2.75L10.2 11.9l2.75-1.05L14 8.1z" fill="#015253" />
          </svg>
        </button>
      )}

      {/* Panel */}
      {open && (
        <div className="fixed bottom-5 right-5 z-50 w-[calc(100vw-2.5rem)] sm:w-[358px] h-[540px] max-h-[calc(100dvh-2.5rem)] bg-white rounded-[20px] shadow-2xl border border-[#015253]/10 flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-3.5 py-3 bg-[#015253] text-white shadow-[inset_0_-1px_0_rgba(255,255,255,0.08)]">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-white/20 flex items-center justify-center">
                <Bot className="w-5 h-5" />
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
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-3.5 space-y-3 bg-[#f5f8f7]">
            {messages.length === 0 && (
              <div className="text-center pt-6">
                <div className="w-12 h-12 mx-auto rounded-2xl bg-[#d3e6e5] flex items-center justify-center mb-3">
                  <Sparkles className="w-6 h-6 text-[#015253]" />
                </div>
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
                        ? 'bg-[#015253] text-white rounded-2xl rounded-br-sm px-3.5 py-2.5 text-sm'
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
              <div className="flex items-center gap-2 text-slate-400 text-sm">
                <Loader2 className="w-4 h-4 animate-spin" />
                Thinking…
              </div>
            )}
          </div>

          {/* Suggestion / refine chips */}
          {(messages.length === 0 ? suggestions : activeRefine).length > 0 && (
            <div className="px-3 pt-2.5 pb-1 bg-slate-50 border-t border-slate-100 flex flex-wrap gap-1.5">
              {(messages.length === 0 ? suggestions : activeRefine).slice(0, 5).map((s) => (
                <button
                  key={s}
                  onClick={() => (messages.length === 0 ? send(s) : send(s, true))}
                  className="text-left px-2.5 py-1.5 text-xs bg-white border border-slate-200 rounded-full hover:border-[#4d8a8a] hover:text-[#015253] text-slate-600 transition-colors"
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
            className="p-3 bg-white border-t border-slate-200 flex gap-2"
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your question…"
              disabled={loading}
              className="flex-1 px-3.5 py-2.5 text-sm bg-slate-100 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#015253] focus:bg-white transition-all"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="w-10 h-10 flex items-center justify-center bg-[#015253] text-white rounded-xl hover:bg-[#013b3c] disabled:bg-slate-300 transition-colors"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      )}
    </>
  );
}
