import { useState, useRef, useEffect } from 'react';
import ChatWidget from '../components/ChatWidget';
import { ExternalLink, Loader2 } from 'lucide-react';

// The live storefront is served through our backend proxy (/api/site/...), which
// strips the site's X-Frame-Options/CSP so it can be framed. Because it's then
// same-origin, we can also read the iframe's URL to know which category page the
// visitor is on and tailor the assistant's suggested questions.
const PROXY_ROOT = '/api/site/';

// Map the real site's category slugs to the catalog categories we have
// suggestions for.
const CATEGORY_BY_SLUG: { match: string; category: string }[] = [
  { match: 'tuerklingel', category: 'Doorbells' },
  { match: 'klingelschild', category: 'Doorbells' },
  { match: 'briefkasten', category: 'Mailboxes' },
  { match: 'tuersprechanlagen', category: 'Intercoms' },
  { match: 'sprechanlage', category: 'Intercoms' },
  { match: 'paketbox', category: 'Package Boxes' },
  { match: 'paketkasten', category: 'Package Boxes' },
  { match: 'hausnummer', category: 'House Numbers' },
];

function detectCategory(pathname: string): string | null {
  const p = pathname.toLowerCase();
  const hit = CATEGORY_BY_SLUG.find((c) => p.includes(c.match));
  return hit ? hit.category : null;
}

export default function Store() {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [category, setCategory] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // On each in-frame navigation, re-read the path to update the chat context.
  const handleLoad = () => {
    setLoading(false);
    try {
      const path = iframeRef.current?.contentWindow?.location?.pathname || '';
      setCategory(detectCategory(path));
    } catch {
      // Cross-origin (shouldn't happen via the proxy) — keep global suggestions.
      setCategory(null);
    }
  };

  // Poll the iframe location too: some in-site navigations don't refire onLoad.
  useEffect(() => {
    const id = setInterval(() => {
      try {
        const path = iframeRef.current?.contentWindow?.location?.pathname || '';
        const next = detectCategory(path);
        setCategory((prev) => (prev === next ? prev : next));
      } catch {
        /* ignore */
      }
    }, 1500);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="relative">
      {/* Thin context bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-slate-200 text-sm">
        <div className="flex items-center gap-2 text-slate-500">
          <span className="w-2 h-2 rounded-full bg-emerald-500" />
          Live storefront
          {category && (
            <span className="ml-1 px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 text-xs font-medium">
              {category}
            </span>
          )}
        </div>
        <a
          href="https://edelstahl-tuerklingel.de"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 text-slate-500 hover:text-indigo-600 transition-colors"
        >
          Open original <ExternalLink className="w-3.5 h-3.5" />
        </a>
      </div>

      {loading && (
        <div className="absolute inset-0 top-10 flex items-center justify-center bg-slate-50 z-10">
          <div className="flex items-center gap-2 text-slate-400">
            <Loader2 className="w-5 h-5 animate-spin" />
            Loading storefront…
          </div>
        </div>
      )}

      <iframe
        ref={iframeRef}
        src={PROXY_ROOT}
        onLoad={handleLoad}
        title="Storefront"
        className="w-full border-0 bg-white"
        style={{ height: 'calc(100vh - 6.5rem)' }}
      />

      {/* Assistant popup, overlaid on the storefront, aware of the current category */}
      <ChatWidget category={category} />
    </div>
  );
}
