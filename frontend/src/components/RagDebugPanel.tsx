import { useState } from 'react';
import { ChevronDown, ChevronRight, Bug } from 'lucide-react';
import { RagDebug } from '../types';

interface Props {
  debug: RagDebug;
}

// Collapsible panel that exposes every step of the RAG pipeline for a single
// query: retrieval config, the vector-search hits with scores, the exact
// prompt sent to the LLM, and its raw JSON response. Meant for the PoC so the
// pipeline is inspectable, not just the final answer.
export default function RagDebugPanel({ debug }: Props) {
  const [open, setOpen] = useState(false);

  const steps = debug.steps || [];
  const retrievalConfig = steps.find((s) => s.step === '1_retrieval_config');
  const vectorSearch = steps.find((s) => s.step === '2_vector_search');
  const llmPrompt = steps.find((s) => s.step === '3_llm_prompt');
  const llmResponse = steps.find((s) => s.step === '4_llm_response');
  const finalProducts = steps.find((s) => s.step === '5_final_products');

  const box = 'bg-gray-900 text-gray-100 rounded-md p-3 text-xs overflow-x-auto whitespace-pre-wrap font-mono';

  return (
    <div className="bg-white rounded-lg shadow border border-gray-200">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-6 py-4 text-left text-gray-800 hover:bg-gray-50 rounded-lg transition-colors"
      >
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        <Bug className="w-4 h-4 text-purple-600" />
        <span className="font-semibold">RAG Trace</span>
        <span className="text-sm text-gray-500">
          (embed: {debug.embedding_model || 'n/a'}
          {llmPrompt?.model ? ` · llm: ${llmPrompt.model}` : ''})
        </span>
      </button>

      {open && (
        <div className="px-6 pb-6 space-y-5">
          {/* Step 1 – retrieval config */}
          <section>
            <h4 className="text-sm font-semibold text-gray-900 mb-2">
              1. Retrieval config
            </h4>
            <div className={box}>
              {retrievalConfig
                ? JSON.stringify(
                    {
                      num_retrieved: retrievalConfig.num_retrieved,
                      similarity_threshold: retrievalConfig.similarity_threshold,
                      enable_metadata_filters: retrievalConfig.enable_metadata_filters,
                    },
                    null,
                    2
                  )
                : 'n/a'}
            </div>
          </section>

          {/* Step 2 – vector search */}
          <section>
            <h4 className="text-sm font-semibold text-gray-900 mb-2">
              2. Vector search — {vectorSearch?.retrieved_count ?? 0} hits from Qdrant
              {vectorSearch?.embedding_model ? ` (${vectorSearch.embedding_model})` : ''}
            </h4>
            <div className="overflow-x-auto">
              <table className="w-full text-xs border border-gray-200 rounded">
                <thead className="bg-gray-100 text-gray-700">
                  <tr>
                    <th className="text-left px-2 py-1">#</th>
                    <th className="text-left px-2 py-1">product_id</th>
                    <th className="text-left px-2 py-1">name</th>
                    <th className="text-left px-2 py-1">category</th>
                    <th className="text-right px-2 py-1">score</th>
                  </tr>
                </thead>
                <tbody>
                  {(vectorSearch?.results || []).map((r: any, i: number) => (
                    <tr key={r.product_id} className="border-t border-gray-100">
                      <td className="px-2 py-1 text-gray-500">{i + 1}</td>
                      <td className="px-2 py-1 font-mono">{r.product_id}</td>
                      <td className="px-2 py-1">{r.name}</td>
                      <td className="px-2 py-1 text-gray-600">{r.category}</td>
                      <td className="px-2 py-1 text-right font-mono">{r.score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* Step 3 – prompt sent to the LLM */}
          <section>
            <h4 className="text-sm font-semibold text-gray-900 mb-2">
              3. Prompt sent to the LLM
              {llmPrompt?.model ? ` — ${llmPrompt.model} (temp ${llmPrompt.temperature})` : ''}
            </h4>
            <p className="text-xs text-gray-500 mb-1">System prompt</p>
            <div className={box}>{llmPrompt?.system_prompt || 'n/a'}</div>
            <p className="text-xs text-gray-500 mt-2 mb-1">User message</p>
            <div className={box}>{llmPrompt?.user_message || 'n/a'}</div>
          </section>

          {/* Step 4 – raw LLM response */}
          <section>
            <h4 className="text-sm font-semibold text-gray-900 mb-2">
              4. Raw LLM response
              {llmResponse?.token_usage?.total_tokens
                ? ` — ${llmResponse.token_usage.total_tokens} tokens`
                : ''}
            </h4>
            <div className={box}>{llmResponse?.raw_response || llmResponse?.error || 'n/a'}</div>
            {(llmResponse?.dropped_hallucinated_ids?.length ?? 0) > 0 && (
              <p className="text-xs text-amber-600 mt-1">
                Dropped hallucinated product_ids (not in retrieved set):{' '}
                {llmResponse?.dropped_hallucinated_ids?.join(', ')}
              </p>
            )}
          </section>

          {/* Step 5 – final products */}
          <section>
            <h4 className="text-sm font-semibold text-gray-900 mb-2">
              5. Final products shown ({finalProducts?.recommended_count ?? 0})
            </h4>
            <div className={box}>
              {finalProducts ? JSON.stringify(finalProducts.product_ids, null, 2) : 'n/a'}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
