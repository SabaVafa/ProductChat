import { useEffect, useState } from 'react';
import { chatAPI } from '../services/api';
import { ThumbsUp, ThumbsDown, RefreshCw, Filter, MessagesSquare, Minus } from 'lucide-react';

interface Retrieved {
  product_id: string;
  name: string;
  score?: number;
}

interface Interaction {
  id: number;
  message: string;
  retrieval_query?: string;
  answer?: string;
  recommended_ids?: string[];
  retrieved?: Retrieved[];
  feedback?: number | null; // 1, -1, or null
  created_at?: string;
}

interface Data {
  total: number;
  thumbs_up: number;
  thumbs_down: number;
  items: Interaction[];
}

function timeAgo(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return '';
  const s = Math.floor((Date.now() - d) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function Conversations() {
  const [data, setData] = useState<Data | null>(null);
  const [loading, setLoading] = useState(true);
  const [onlyDown, setOnlyDown] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await chatAPI.getInteractions(200));
    } catch (e: any) {
      setError('Could not load conversations. Is the backend running?');
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const items = (data?.items ?? []).filter((it) => (onlyDown ? it.feedback === -1 : true));
  const helpfulness =
    data && data.thumbs_up + data.thumbs_down > 0
      ? Math.round((100 * data.thumbs_up) / (data.thumbs_up + data.thumbs_down))
      : null;

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-100 flex items-center justify-center">
            <MessagesSquare className="w-5 h-5 text-indigo-600" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-slate-900">Conversations</h1>
            <p className="text-sm text-slate-500">Every chat is logged — review answers and their feedback.</p>
          </div>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-100 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Stat tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <p className="text-2xl font-bold text-slate-900 tabular-nums">{data?.total ?? '—'}</p>
          <p className="text-xs text-slate-500 mt-0.5">Total chats</p>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <p className="text-2xl font-bold text-emerald-600 tabular-nums">{data?.thumbs_up ?? '—'}</p>
          <p className="text-xs text-slate-500 mt-0.5">Thumbs up</p>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <p className="text-2xl font-bold text-rose-600 tabular-nums">{data?.thumbs_down ?? '—'}</p>
          <p className="text-xs text-slate-500 mt-0.5">Thumbs down</p>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <p className="text-2xl font-bold text-indigo-600 tabular-nums">
            {helpfulness === null ? '—' : `${helpfulness}%`}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">Helpful (of rated)</p>
        </div>
      </div>

      {/* Filter */}
      <div className="flex items-center justify-between mb-3">
        <button
          onClick={() => setOnlyDown((v) => !v)}
          className={`flex items-center gap-2 px-3 py-1.5 text-sm rounded-full border transition-colors ${
            onlyDown
              ? 'bg-rose-50 border-rose-200 text-rose-700'
              : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-100'
          }`}
        >
          <Filter className="w-3.5 h-3.5" />
          {onlyDown ? 'Showing only 👎' : 'Show only 👎'}
        </button>
        <span className="text-xs text-slate-400">{items.length} shown</span>
      </div>

      {/* List */}
      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-700 rounded-lg p-4 text-sm">{error}</div>
      )}

      {!error && !loading && items.length === 0 && (
        <div className="text-center py-16 text-slate-400">
          <MessagesSquare className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p className="text-sm">{onlyDown ? 'No thumbs-down conversations yet.' : 'No conversations logged yet.'}</p>
        </div>
      )}

      <div className="space-y-3">
        {items.map((it) => (
          <div key={it.id} className="bg-white border border-slate-200 rounded-xl p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-900 break-words">{it.message}</p>
                {it.retrieval_query && it.retrieval_query !== it.message && (
                  <p className="text-[11px] text-slate-400 mt-0.5 font-mono break-words">
                    searched: {it.retrieval_query}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {it.feedback === 1 && (
                  <span className="flex items-center gap-1 text-xs text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-full px-2 py-0.5">
                    <ThumbsUp className="w-3 h-3" /> Helpful
                  </span>
                )}
                {it.feedback === -1 && (
                  <span className="flex items-center gap-1 text-xs text-rose-700 bg-rose-50 border border-rose-100 rounded-full px-2 py-0.5">
                    <ThumbsDown className="w-3 h-3" /> Not helpful
                  </span>
                )}
                {(it.feedback === null || it.feedback === undefined) && (
                  <span className="flex items-center gap-1 text-xs text-slate-400">
                    <Minus className="w-3 h-3" /> no rating
                  </span>
                )}
                <span className="text-[11px] text-slate-400 whitespace-nowrap">{timeAgo(it.created_at)}</span>
              </div>
            </div>

            {it.answer && <p className="text-sm text-slate-600 mt-2 line-clamp-3">{it.answer}</p>}

            {it.retrieved && it.retrieved.length > 0 && (
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {it.retrieved.slice(0, 6).map((r, idx) => {
                  const recommended = it.recommended_ids?.includes(r.product_id);
                  return (
                    <span
                      key={`${r.product_id}-${idx}`}
                      title={r.score != null ? `score ${r.score.toFixed(3)}` : undefined}
                      className={`text-[11px] rounded-md px-1.5 py-0.5 border ${
                        recommended
                          ? 'bg-indigo-50 border-indigo-200 text-indigo-700 font-medium'
                          : 'bg-slate-50 border-slate-200 text-slate-500'
                      }`}
                    >
                      {r.name || r.product_id}
                    </span>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>

      {items.length > 0 && (
        <p className="text-[11px] text-slate-400 mt-4">
          Highlighted chips were recommended to the user; the rest were retrieved but not shown.
        </p>
      )}
    </div>
  );
}
