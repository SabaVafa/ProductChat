import { useState } from 'react';
import { Copy, Check, Download } from 'lucide-react';

interface Props {
  data: unknown;
  filename?: string;
  maxHeight?: string;
}

// Raw JSON viewer with copy + download — used across the Explorer so any
// retrieved data set can be inspected or exported verbatim.
export default function JsonView({ data, filename = 'data.json', maxHeight = '32rem' }: Props) {
  const [copied, setCopied] = useState(false);
  const text = JSON.stringify(data, null, 2);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (e) {
      console.error('copy failed', e);
    }
  };

  const download = () => {
    const blob = new Blob([text], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="relative">
      <div className="absolute right-2 top-2 flex gap-1.5 z-10">
        <button
          onClick={copy}
          className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs bg-slate-700 text-slate-100 rounded-md hover:bg-slate-600 transition-colors"
        >
          {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? 'Copied' : 'Copy'}
        </button>
        <button
          onClick={download}
          className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs bg-slate-700 text-slate-100 rounded-md hover:bg-slate-600 transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
          Download
        </button>
      </div>
      <pre
        className="bg-slate-900 text-slate-100 rounded-lg p-4 pt-12 text-xs overflow-auto font-mono leading-relaxed"
        style={{ maxHeight }}
      >
        {text}
      </pre>
    </div>
  );
}
