import { useState, useEffect } from 'react';
import { Send, Loader2, Sparkles } from 'lucide-react';
import { chatAPI, suggestionsAPI } from '../services/api';
import { ChatResponse } from '../types';
import ProductCard from '../components/ProductCard';
import RagDebugPanel from '../components/RagDebugPanel';

export default function Chat() {
  const [message, setMessage] = useState('');
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [starters, setStarters] = useState<string[]>([]);

  useEffect(() => {
    suggestionsAPI
      .get()
      .then(setStarters)
      .catch((err) => console.error('Failed to load suggestions:', err));
  }, []);

  const [lastQuery, setLastQuery] = useState('');

  const sendQuery = async (text: string, isRefinement = false) => {
    const q = text.trim();
    if (!q) return;

    setLoading(true);
    setError(null);
    // Keep the previous answer visible while loading — clearing it here meant
    // an error wiped the old answer too (audit finding L4).

    try {
      // A refine chip must carry the conversation context, mirroring the
      // storefront widget — otherwise "Mit LED" arrives as a cold query.
      const history = isRefinement && response
        ? [
            { role: 'user', content: lastQuery },
            { role: 'assistant', content: response.answer },
          ]
        : [];
      const result = await chatAPI.sendMessage(q, history, isRefinement);
      setResponse(result);
      setLastQuery(q);
      setMessage('');
    } catch (err) {
      setError('Failed to get response. Please try again.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendQuery(message);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Product Recommendation Assistant
          </h1>
          <p className="text-gray-600">
            Ask me anything about products and I'll help you find the best matches.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="mb-8">
          <div className="flex gap-2">
            <input
              type="text"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="e.g., a stainless steel mailbox with engraving, or 'Türklingel mit LED'"
              className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !message.trim()}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
            >
              {loading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Thinking...
                </>
              ) : (
                <>
                  <Send className="w-5 h-5" />
                  Send
                </>
              )}
            </button>
          </div>
        </form>

        {/* Prepared starter questions (LLM-generated + templates, cached) */}
        {!response && !loading && starters.length > 0 && (
          <div className="mb-8">
            <div className="flex items-center gap-2 text-sm text-gray-500 mb-3">
              <Sparkles className="w-4 h-4 text-purple-600" />
              Try one of these
            </div>
            <div className="flex flex-wrap gap-2">
              {starters.map((s) => (
                <button
                  key={s}
                  onClick={() => sendQuery(s)}
                  className="px-3 py-2 text-sm bg-white border border-gray-300 rounded-full hover:border-blue-500 hover:text-blue-600 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
            {error}
          </div>
        )}

        {response && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-3 text-gray-900">Answer</h2>
              <p className="text-gray-700 whitespace-pre-wrap">{response.answer}</p>
            </div>

            {response.products.length > 0 && (
              <div>
                <h2 className="text-xl font-semibold mb-4 text-gray-900">
                  Recommended Products ({response.products.length})
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {response.products.map((product) => (
                    <ProductCard key={product.id} product={product} />
                  ))}
                </div>
              </div>
            )}

            {response.follow_up_question && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <p className="text-blue-900 font-medium">{response.follow_up_question}</p>
              </div>
            )}

            {/* Cheap, template-based refine chips derived from this result */}
            {response.refine_suggestions && response.refine_suggestions.length > 0 && (
              <div>
                <p className="text-sm text-gray-500 mb-2">Refine your search</p>
                <div className="flex flex-wrap gap-2">
                  {response.refine_suggestions.map((s) => (
                    <button
                      key={s}
                      onClick={() => sendQuery(s, true)}
                      className="px-3 py-1.5 text-sm bg-gray-100 border border-gray-200 rounded-full hover:bg-blue-50 hover:text-blue-600 hover:border-blue-300 transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {response.debug && <RagDebugPanel debug={response.debug} />}
          </div>
        )}
      </div>
    </div>
  );
}
