import { useState, useEffect, Fragment } from 'react';
import { productsAPI, testAPI, ProductFilters } from '../services/api';
import JsonView from '../components/JsonView';
import { safeUrl, formatPrice } from '../utils/format';
import {
  Database, Search, Play, Loader2, ExternalLink, CheckCircle2, XCircle,
  Table as TableIcon, Braces, Layers, ChevronRight, ChevronDown, Tag, X,
} from 'lucide-react';

const PAGE_SIZE = 25;

export default function Explorer() {
  const [tab, setTab] = useState<'data' | 'topics' | 'playground'>('data');

  const tabs = [
    { id: 'data', label: 'Catalog data', icon: Database },
    { id: 'topics', label: 'Topics & groups', icon: Layers },
    { id: 'playground', label: 'Retrieval playground', icon: Play },
  ] as const;

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 mb-1">Data Explorer</h1>
        <p className="text-slate-500">
          Inspect the indexed catalog as raw JSON, filter and group it, and test what the vector
          search returns.
        </p>
      </div>

      <div className="flex gap-1 mb-6 bg-slate-100 p-1 rounded-lg w-fit">
        {tabs.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                tab === t.id ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              <Icon className="w-4 h-4" /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === 'data' && <DataTab />}
      {tab === 'topics' && <TopicsTab />}
      {tab === 'playground' && <PlaygroundTab />}
    </div>
  );
}

/* ------------------------------- Catalog data ------------------------------ */

function DataTab() {
  const [filters, setFilters] = useState<ProductFilters>({});
  const [searchInput, setSearchInput] = useState('');
  const [rows, setRows] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState<'table' | 'json'>('table');
  const [groupBy, setGroupBy] = useState<'' | 'category' | 'brand' | 'source'>('');
  const [facets, setFacets] = useState<any>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    productsAPI.facets().then(setFacets).catch(console.error);
  }, []);

  const load = async (nextOffset: number, replace: boolean, f: ProductFilters = filters) => {
    setLoading(true);
    try {
      const data = await productsAPI.list({ ...f, limit: PAGE_SIZE, offset: nextOffset });
      setRows((prev) => (replace ? data.products : [...prev, ...data.products]));
      setTotal(data.total);
      setOffset(nextOffset + data.products.length);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(0, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

  const setFilter = (key: keyof ProductFilters, value: any) =>
    setFilters((f) => ({ ...f, [key]: value === '' ? undefined : value }));

  const clearFilters = () => {
    setFilters({});
    setSearchInput('');
  };

  const activeCount = Object.values(filters).filter((v) => v !== undefined && v !== '').length;
  const opts = (name: string) =>
    (facets?.groups?.[name] || []).filter((g: any) => g.value !== '(none)');

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 space-y-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setFilter('search', searchInput);
          }}
          className="flex gap-2"
        >
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search name, description, brand or id…"
              className="w-full pl-9 pr-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <button className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700">
            Search
          </button>
        </form>

        <div className="flex flex-wrap gap-2 items-center">
          <Select label="Category" value={filters.category || ''} onChange={(v) => setFilter('category', v)} options={opts('category')} />
          <Select label="Brand" value={filters.brand || ''} onChange={(v) => setFilter('brand', v)} options={opts('brand')} />
          <Select label="Source" value={filters.source || ''} onChange={(v) => setFilter('source', v)} options={opts('source')} />

          <select
            value={filters.indexed === undefined ? '' : String(filters.indexed)}
            onChange={(e) => setFilter('indexed', e.target.value === '' ? undefined : e.target.value === 'true')}
            className="px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">Indexed: any</option>
            <option value="true">Indexed only</option>
            <option value="false">Not indexed</option>
          </select>

          <input
            type="number"
            placeholder="Min €"
            value={filters.min_price ?? ''}
            onChange={(e) => setFilter('min_price', e.target.value === '' ? undefined : +e.target.value)}
            className="w-24 px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <input
            type="number"
            placeholder="Max €"
            value={filters.max_price ?? ''}
            onChange={(e) => setFilter('max_price', e.target.value === '' ? undefined : +e.target.value)}
            className="w-24 px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />

          <select
            value={groupBy}
            onChange={(e) => setGroupBy(e.target.value as any)}
            className="px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">No grouping</option>
            <option value="category">Group by category</option>
            <option value="brand">Group by brand</option>
            <option value="source">Group by source</option>
          </select>

          {activeCount > 0 && (
            <button
              onClick={clearFilters}
              className="flex items-center gap-1 px-3 py-2 text-sm text-slate-500 hover:text-red-600"
            >
              <X className="w-4 h-4" /> Clear ({activeCount})
            </button>
          )}

          <div className="ml-auto flex gap-1 bg-slate-100 p-1 rounded-lg">
            <button
              onClick={() => setView('table')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium ${view === 'table' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500'}`}
            >
              <TableIcon className="w-3.5 h-3.5" /> Table
            </button>
            <button
              onClick={() => setView('json')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium ${view === 'json' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500'}`}
            >
              <Braces className="w-3.5 h-3.5" /> JSON
            </button>
          </div>
        </div>
      </div>

      {/* Grouped view */}
      {groupBy ? (
        <GroupedList groupBy={groupBy} facets={facets} filters={filters} />
      ) : view === 'json' ? (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
          <p className="text-sm text-slate-500 mb-3">
            {rows.length} of {total} records (raw JSON, exactly as stored & indexed)
          </p>
          <JsonView data={rows} filename="catalog.json" />
          {offset < total && (
            <button
              onClick={() => load(offset, false)}
              disabled={loading}
              className="mt-3 inline-flex items-center gap-2 px-4 py-2 border border-slate-300 rounded-lg text-sm hover:border-indigo-400"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />} Load more into JSON
            </button>
          )}
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-left">
                <tr>
                  <th className="px-3 py-2.5 w-8" />
                  <th className="px-4 py-2.5 font-medium">Name</th>
                  <th className="px-4 py-2.5 font-medium">Category</th>
                  <th className="px-4 py-2.5 font-medium">Brand</th>
                  <th className="px-4 py-2.5 font-medium">Source</th>
                  <th className="px-4 py-2.5 font-medium text-right">Price</th>
                  <th className="px-4 py-2.5 font-medium text-center">Indexed</th>
                  <th className="px-4 py-2.5 font-medium text-center">Link</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <Fragment key={p.product_id}>
                    <tr
                      className="border-t border-slate-100 hover:bg-slate-50 cursor-pointer"
                      onClick={() => setExpanded(expanded === p.product_id ? null : p.product_id)}
                    >
                      <td className="px-3 py-2.5 text-slate-400">
                        {expanded === p.product_id ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                      </td>
                      <td className="px-4 py-2.5 text-slate-900 max-w-xs">
                        <span className="line-clamp-1">{p.name}</span>
                        <span className="text-xs text-slate-400 font-mono">{p.product_id}</span>
                      </td>
                      <td className="px-4 py-2.5 text-slate-600">{p.category || '—'}</td>
                      <td className="px-4 py-2.5 text-slate-600">{p.brand || '—'}</td>
                      <td className="px-4 py-2.5 text-slate-500 text-xs">{p.source || '—'}</td>
                      <td className="px-4 py-2.5 text-right font-medium">
                        {p.price != null ? formatPrice(Number(p.price)) : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        {p.indexed ? <CheckCircle2 className="w-4 h-4 text-emerald-500 inline" /> : <XCircle className="w-4 h-4 text-slate-300 inline" />}
                      </td>
                      <td className="px-4 py-2.5 text-center" onClick={(e) => e.stopPropagation()}>
                        {safeUrl(p.product_url) ? (
                          <a href={safeUrl(p.product_url)} target="_blank" rel="noopener noreferrer" className="text-indigo-600 inline-flex">
                            <ExternalLink className="w-4 h-4" />
                          </a>
                        ) : (
                          <span className="text-slate-300">—</span>
                        )}
                      </td>
                    </tr>
                    {expanded === p.product_id && (
                      <tr className="bg-slate-50">
                        <td colSpan={8} className="px-4 py-3">
                          <JsonView data={p} filename={`${p.product_id}.json`} maxHeight="20rem" />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          <div className="p-4 flex items-center justify-between text-sm text-slate-500">
            <span>Showing {rows.length} of {total}</span>
            {offset < total && (
              <button
                onClick={() => load(offset, false)}
                disabled={loading}
                className="inline-flex items-center gap-2 px-4 py-2 border border-slate-300 rounded-lg hover:border-indigo-400"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />} Load more
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Select({
  label, value, onChange, options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; count: number }[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
    >
      <option value="">{label}: all</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.value} ({o.count})
        </option>
      ))}
    </select>
  );
}

/* Collapsible group-by list: counts come from /facets, items load on expand. */
function GroupedList({ groupBy, facets, filters }: { groupBy: string; facets: any; filters: ProductFilters }) {
  const [open, setOpen] = useState<string | null>(null);
  const [items, setItems] = useState<Record<string, any[]>>({});
  const [loading, setLoading] = useState<string | null>(null);

  const groups = facets?.groups?.[groupBy] || [];

  const toggle = async (value: string) => {
    if (open === value) {
      setOpen(null);
      return;
    }
    setOpen(value);
    if (!items[value]) {
      setLoading(value);
      try {
        const data = await productsAPI.list({
          ...filters,
          [groupBy]: value === '(none)' ? undefined : value,
          limit: 200,
        });
        setItems((prev) => ({ ...prev, [value]: data.products }));
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(null);
      }
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm divide-y divide-slate-100">
      {groups.length === 0 && <p className="p-6 text-slate-400 text-sm">No groups.</p>}
      {groups.map((g: any) => (
        <div key={g.value}>
          <button
            onClick={() => toggle(g.value)}
            className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-50 text-left"
          >
            <span className="flex items-center gap-2 text-sm font-medium text-slate-800">
              {open === g.value ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
              {g.value}
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">{g.count}</span>
          </button>
          {open === g.value && (
            <div className="px-4 pb-4">
              {loading === g.value ? (
                <div className="flex items-center gap-2 text-slate-400 text-sm py-3">
                  <Loader2 className="w-4 h-4 animate-spin" /> Loading…
                </div>
              ) : (
                <JsonView data={items[g.value] || []} filename={`${groupBy}-${g.value}.json`} maxHeight="24rem" />
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ----------------------------- Topics & groups ----------------------------- */

function TopicsTab() {
  const [facets, setFacets] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [raw, setRaw] = useState(false);

  useEffect(() => {
    productsAPI
      .facets()
      .then(setFacets)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-slate-400 py-12 justify-center">
        <Loader2 className="w-5 h-5 animate-spin" /> Loading catalog topics…
      </div>
    );
  }
  if (!facets) return <p className="text-slate-400">Could not load facets.</p>;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex gap-3">
          <Stat label="Products" value={facets.total} />
          <Stat label="Indexed" value={facets.indexed} tone="emerald" />
          <Stat label="Not indexed" value={facets.not_indexed} tone="amber" />
        </div>
        <button
          onClick={() => setRaw(!raw)}
          className="flex items-center gap-1.5 px-3 py-2 text-sm border border-slate-300 rounded-lg hover:border-indigo-400"
        >
          <Braces className="w-4 h-4" /> {raw ? 'Show cards' : 'Show JSON'}
        </button>
      </div>

      {raw ? (
        <JsonView data={facets} filename="facets.json" maxHeight="40rem" />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <GroupCard title="Categories" items={facets.groups.category} />
          <GroupCard title="Brands" items={facets.groups.brand} />
          <GroupCard title="Source" items={facets.groups.source} />
          <GroupCard title="Price ranges" items={facets.price.buckets.map((b: any) => ({ value: b.range, count: b.count }))} />

          <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 shadow-sm p-5">
            <h3 className="font-semibold text-slate-900 mb-1 flex items-center gap-2">
              <Tag className="w-4 h-4 text-indigo-600" /> Attribute topics
            </h3>
            <p className="text-xs text-slate-400 mb-4">
              Attribute keys attached to products, with their most common values. These are the
              structured "topics" the embeddings are built from.
            </p>
            {facets.attributes.length === 0 ? (
              <p className="text-sm text-slate-400">
                No attributes found. (Scraped products don't carry attributes yet — only imported ones do.)
              </p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {facets.attributes.map((a: any) => (
                  <div key={a.key} className="border border-slate-100 rounded-lg p-3">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-slate-800">{a.key}</span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">{a.count}</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {a.top_values.map((v: any) => (
                        <span key={v.value} className="text-xs px-2 py-1 bg-slate-100 text-slate-600 rounded-md">
                          {v.value} <span className="text-slate-400">×{v.count}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, tone = 'slate' }: { label: string; value: number; tone?: string }) {
  const tones: Record<string, string> = {
    slate: 'text-slate-900',
    emerald: 'text-emerald-600',
    amber: 'text-amber-600',
  };
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm px-5 py-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`text-2xl font-bold ${tones[tone]}`}>{value}</p>
    </div>
  );
}

function GroupCard({ title, items }: { title: string; items: { value: string; count: number }[] }) {
  const max = Math.max(...items.map((i) => i.count), 1);
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
      <h3 className="font-semibold text-slate-900 mb-3">{title}</h3>
      {items.length === 0 ? (
        <p className="text-sm text-slate-400">None.</p>
      ) : (
        <div className="space-y-2">
          {items.map((i) => (
            <div key={i.value} className="flex items-center gap-3">
              <span className="text-sm text-slate-700 w-40 truncate">{i.value}</span>
              <div className="flex-1 h-2 bg-slate-100 rounded-full">
                <div className="h-2 bg-indigo-500 rounded-full" style={{ width: `${(i.count / max) * 100}%` }} />
              </div>
              <span className="text-xs text-slate-500 w-10 text-right">{i.count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* --------------------------- Retrieval playground -------------------------- */

function PlaygroundTab() {
  const [query, setQuery] = useState('');
  const [limit, setLimit] = useState(10);
  const [threshold, setThreshold] = useState(0);
  const [results, setResults] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState<'list' | 'json'>('list');

  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await testAPI.testRetrieval(query, limit, threshold);
      setResults(data.products || []);
    } catch (err) {
      console.error(err);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
        <p className="text-sm text-slate-500 mb-3">
          Runs the raw vector search only (no LLM) — exactly the retrieval step the assistant uses.
          Switch to JSON to see the full payload each match carries.
        </p>
        <form onSubmit={run} className="space-y-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. mailbox with newspaper compartment, or 'Türklingel mit LED'"
            className="w-full px-3.5 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <div className="flex flex-wrap items-end gap-4">
            <label className="text-sm text-slate-600">
              <span className="block mb-1">Results: {limit}</span>
              <input type="range" min={1} max={25} value={limit} onChange={(e) => setLimit(+e.target.value)} />
            </label>
            <label className="text-sm text-slate-600">
              <span className="block mb-1">Min score: {threshold.toFixed(2)}</span>
              <input type="range" min={0} max={1} step={0.05} value={threshold} onChange={(e) => setThreshold(+e.target.value)} />
            </label>
            <button
              disabled={loading || !query.trim()}
              className="ml-auto inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700 disabled:bg-slate-300"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Run query
            </button>
          </div>
        </form>
      </div>

      {results && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
          <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
            <span className="text-sm font-medium text-slate-700">
              {results.length} result{results.length !== 1 ? 's' : ''}
            </span>
            <div className="flex gap-1 bg-slate-100 p-1 rounded-lg">
              <button
                onClick={() => setView('list')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium ${view === 'list' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500'}`}
              >
                <TableIcon className="w-3.5 h-3.5" /> Ranked
              </button>
              <button
                onClick={() => setView('json')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium ${view === 'json' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500'}`}
              >
                <Braces className="w-3.5 h-3.5" /> JSON
              </button>
            </div>
          </div>

          {results.length === 0 ? (
            <div className="p-8 text-center text-slate-400 text-sm">No matches. Try lowering the min score.</div>
          ) : view === 'json' ? (
            <div className="p-4">
              <JsonView data={results} filename="retrieval-results.json" />
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {results.map((p, i) => (
                <div key={p.product_id} className="flex items-center gap-3 px-4 py-3">
                  <span className="w-6 text-slate-400 text-sm">{i + 1}</span>
                  {p.image_url && (
                    <img src={p.image_url} alt="" className="w-10 h-10 rounded object-cover bg-slate-100" onError={(e) => (e.currentTarget.style.display = 'none')} />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-slate-900 line-clamp-1">{p.name}</p>
                    <p className="text-xs text-slate-400">
                      {p.category} · {p.brand || '—'} · {p.price != null ? formatPrice(Number(p.price)) : '—'}
                    </p>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-mono font-semibold text-indigo-600">{Number(p.score).toFixed(4)}</div>
                    <div className="w-24 h-1.5 bg-slate-100 rounded-full mt-1">
                      <div className="h-1.5 bg-indigo-500 rounded-full" style={{ width: `${Math.min(100, p.score * 100)}%` }} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
