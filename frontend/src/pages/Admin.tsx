import { useState, useEffect } from 'react';
import { Settings as SettingsType } from '../types';
import { settingsAPI, indexingAPI, syncAPI, opsAPI } from '../services/api';
import { Save, RefreshCw, Upload, Database, Brain, Search, Sliders, Globe, ScrollText } from 'lucide-react';

export default function Admin() {
  const [settings, setSettings] = useState<SettingsType | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [indexingStatus, setIndexingStatus] = useState<any>(null);
  const [syncStatus, setSyncStatus] = useState<any>(null);
  const [bestsellerStatus, setBestsellerStatus] = useState<any>(null);
  const [ops, setOps] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState('mistral');

  useEffect(() => {
    loadSettings();
    loadIndexingStatus();
    loadSyncStatus();
    loadBestsellerStatus();
    opsAPI.list(15).then(setOps).catch((e) => console.error('ops load failed', e));
  }, []);

  const loadBestsellerStatus = async () => {
    try {
      setBestsellerStatus(await indexingAPI.getBestsellerStatus());
    } catch (error) {
      console.error('Failed to load bestseller status:', error);
    }
  };

  // Poll bestseller-capture status while a capture is running.
  useEffect(() => {
    if (bestsellerStatus?.status !== 'running') return;
    const interval = setInterval(loadBestsellerStatus, 1500);
    return () => clearInterval(interval);
  }, [bestsellerStatus?.status]);

  const handleCaptureBestsellers = async () => {
    try {
      setBestsellerStatus((prev: any) => ({
        ...(prev || {}),
        status: 'running',
        categories_done: 0,
        categories_total: 0,
        products_ranked: 0,
        error: null,
      }));
      await indexingAPI.captureBestsellers();
      loadBestsellerStatus();
    } catch (error) {
      alert('Failed to start bestseller capture');
      console.error(error);
      loadBestsellerStatus();
    }
  };

  const loadSyncStatus = async () => {
    try {
      setSyncStatus(await syncAPI.getStatus());
    } catch (error) {
      console.error('Failed to load sync status:', error);
    }
  };

  // Poll catalog sync status while a sync is running.
  useEffect(() => {
    if (syncStatus?.status !== 'running') return;
    const interval = setInterval(loadSyncStatus, 1500);
    return () => clearInterval(interval);
  }, [syncStatus?.status]);

  const handleSync = async (maxProducts: number) => {
    try {
      // Flip to running immediately so polling starts and buttons disable.
      setSyncStatus((prev: any) => ({
        ...(prev || {}),
        status: 'running',
        phase: 'scanning',
        scanned: 0,
        total_urls: 0,
        products_found: 0,
        changed: 0,
        indexed: 0,
        error: null,
      }));
      await syncAPI.run(maxProducts);
      loadSyncStatus();
    } catch (error) {
      alert('Failed to start sync');
      console.error(error);
      loadSyncStatus();
    }
  };

  // While indexing is running, poll status every second so the processed/total
  // count and progress bar update live (the job runs in the background).
  useEffect(() => {
    if (indexingStatus?.status !== 'running') return;
    const interval = setInterval(loadIndexingStatus, 1000);
    return () => clearInterval(interval);
  }, [indexingStatus?.status]);

  const loadSettings = async () => {
    try {
      const data = await settingsAPI.getSettings();
      setSettings(data);
    } catch (error) {
      console.error('Failed to load settings:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadIndexingStatus = async () => {
    try {
      const status = await indexingAPI.getStatus();
      setIndexingStatus(status);
    } catch (error) {
      console.error('Failed to load indexing status:', error);
    }
  };

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      await settingsAPI.updateSettings(settings);
      alert('Settings saved successfully');
    } catch (error) {
      alert('Failed to save settings');
      console.error(error);
    } finally {
      setSaving(false);
    }
  };

  const handleStartIndexing = async (incremental = false) => {
    try {
      // Optimistically flip to "running" so the polling effect starts and the
      // buttons disable immediately, without waiting for the first poll.
      setIndexingStatus((prev: any) => ({ ...(prev || {}), status: 'running', processed: 0 }));
      await indexingAPI.startIndexing(incremental);
      loadIndexingStatus();
    } catch (error) {
      alert('Failed to start indexing');
      console.error(error);
      loadIndexingStatus();
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      await indexingAPI.importFile(file);
      alert('File imported successfully');
      loadIndexingStatus();
    } catch (error) {
      alert('Failed to import file');
      console.error(error);
    }
  };

  const updateSetting = (category: keyof SettingsType, key: string, value: any) => {
    if (!settings) return;
    setSettings({
      ...settings,
      [category]: {
        ...settings[category],
        [key]: value,
      },
    });
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-600">Loading...</div>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-red-600">Failed to load settings</div>
      </div>
    );
  }

  const tabs = [
    { id: 'mistral', label: 'Mistral AI', icon: Brain },
    { id: 'qdrant', label: 'Vector Database', icon: Database },
    { id: 'retrieval', label: 'Retrieval', icon: Search },
    { id: 'output', label: 'Output Format', icon: Sliders },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Admin Settings</h1>
          <p className="text-gray-600">Configure your AI recommendation system</p>
        </div>

        {/* Catalog Auto-Sync (scraper) */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <div className="flex items-center gap-2 mb-4">
            <Globe className="w-5 h-5 text-purple-600" />
            <h2 className="text-xl font-semibold text-gray-900">Catalog Auto-Sync</h2>
          </div>
          <p className="text-sm text-gray-500 mb-4">
            The catalog is scraped from the source website on a schedule. Only products whose
            content changed since the last run are re-embedded and re-indexed.
          </p>
          {syncStatus && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-sm text-gray-500">Status</p>
                <p className="font-semibold capitalize flex items-center gap-2">
                  {syncStatus.status === 'running' && (
                    <RefreshCw className="w-4 h-4 animate-spin text-purple-600" />
                  )}
                  {syncStatus.status}
                  {syncStatus.phase ? ` · ${syncStatus.phase}` : ''}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Scanned</p>
                <p className="font-semibold">{syncStatus.scanned} / {syncStatus.total_urls}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Changed / Indexed</p>
                <p className="font-semibold">{syncStatus.changed} / {syncStatus.indexed}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Last success</p>
                <p className="font-semibold">
                  {syncStatus.last_success_at
                    ? new Date(syncStatus.last_success_at).toLocaleString()
                    : 'Never'}
                </p>
              </div>
            </div>
          )}
          {/* Scan progress while running */}
          {syncStatus?.status === 'running' && syncStatus.total_urls > 0 && (
            <div className="mt-4">
              <div className="w-full bg-gray-200 rounded-full h-2.5">
                <div
                  className="h-2.5 rounded-full bg-purple-600 transition-all duration-300"
                  style={{
                    width: `${Math.min(100, Math.round((syncStatus.scanned / syncStatus.total_urls) * 100))}%`,
                  }}
                />
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Scanning sitemap ({syncStatus.scanned} of {syncStatus.total_urls} URLs) · found{' '}
                {syncStatus.products_found} products
              </p>
            </div>
          )}

          {syncStatus?.error && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              {syncStatus.error}
            </div>
          )}

          <div className="flex gap-2 flex-wrap mt-4">
            <button
              onClick={() => handleSync(0)}
              disabled={syncStatus?.status === 'running'}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-400 transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${syncStatus?.status === 'running' ? 'animate-spin' : ''}`} />
              Sync now (full catalog)
            </button>
            <button
              onClick={() => handleSync(10)}
              disabled={syncStatus?.status === 'running'}
              className="flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Quick test (10 products)
            </button>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            A full sync scrapes every product page and embeds only the ones that changed. The first
            full run indexes the whole catalog (one embedding call per product).
          </p>
        </div>

        {/* Bestseller rank capture */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <div className="flex items-center gap-2 mb-4">
            <RefreshCw className="w-5 h-5 text-purple-600" />
            <h2 className="text-xl font-semibold text-gray-900">Bestseller Ranks</h2>
          </div>
          <p className="text-sm text-gray-500 mb-4">
            Crawls each category's shop "Bestseller" order and stores a per-product rank, used as a
            relevance-gated tie-break in search. Runs automatically each night; trigger a refresh
            here anytime. No re-embedding — ranks are patched onto the existing index.
          </p>
          {bestsellerStatus && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-sm text-gray-500">Status</p>
                <p className="font-semibold capitalize flex items-center gap-2">
                  {bestsellerStatus.status === 'running' && (
                    <RefreshCw className="w-4 h-4 animate-spin text-purple-600" />
                  )}
                  {bestsellerStatus.status || 'idle'}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Categories</p>
                <p className="font-semibold">
                  {bestsellerStatus.categories_done ?? 0} / {bestsellerStatus.categories_total ?? 0}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Products ranked</p>
                <p className="font-semibold">{bestsellerStatus.products_ranked ?? 0}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Last finished</p>
                <p className="font-semibold">
                  {bestsellerStatus.finished_at
                    ? new Date(bestsellerStatus.finished_at).toLocaleString()
                    : 'Never'}
                </p>
              </div>
            </div>
          )}
          {bestsellerStatus?.status === 'running' && bestsellerStatus.categories_total > 0 && (
            <div className="mt-4">
              <div className="w-full bg-gray-200 rounded-full h-2.5">
                <div
                  className="h-2.5 rounded-full bg-purple-600 transition-all duration-300"
                  style={{
                    width: `${Math.min(100, Math.round((bestsellerStatus.categories_done / bestsellerStatus.categories_total) * 100))}%`,
                  }}
                />
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Crawling categories ({bestsellerStatus.categories_done} of{' '}
                {bestsellerStatus.categories_total})
              </p>
            </div>
          )}
          {bestsellerStatus?.error && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              {bestsellerStatus.error}
            </div>
          )}
          <div className="flex gap-2 flex-wrap mt-4">
            <button
              onClick={handleCaptureBestsellers}
              disabled={bestsellerStatus?.status === 'running'}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-400 transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${bestsellerStatus?.status === 'running' ? 'animate-spin' : ''}`} />
              Refresh bestseller ranks
            </button>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            The shop recomputes bestsellers nightly (~01:00); the automatic capture runs shortly
            after. A manual run takes a few minutes (one polite request per category page).
          </p>
        </div>

        {/* Operations Journal */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <ScrollText className="w-5 h-5 text-purple-600" />
              <h2 className="text-xl font-semibold text-gray-900">Operations Journal</h2>
            </div>
            <button
              onClick={() => opsAPI.list(15).then(setOps).catch(() => {})}
              className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </button>
          </div>
          <p className="text-sm text-gray-500 mb-3">
            Every pipeline run (sync, indexing, import, enrich, dedupe, QA) leaves a permanent record here.
            Detailed error traces are in <code className="bg-gray-100 px-1 rounded">backend/logs/app.log</code>.
          </p>
          {ops.length === 0 ? (
            <p className="text-sm text-gray-400">No operations recorded yet.</p>
          ) : (
            <div className="divide-y divide-gray-100">
              {ops.map((o) => (
                <div key={o.id} className="py-2 flex items-start gap-3 text-sm">
                  <span
                    className={`mt-0.5 px-2 py-0.5 rounded-full text-xs font-medium ${
                      o.status === 'completed'
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-red-50 text-red-700'
                    }`}
                  >
                    {o.kind}
                  </span>
                  <span className="flex-1 text-gray-600 font-mono text-xs break-all">
                    {o.detail ? JSON.stringify(o.detail) : ''}
                  </span>
                  <span className="text-xs text-gray-400 whitespace-nowrap">
                    {o.created_at ? new Date(o.created_at).toLocaleString() : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Indexing Status */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4 text-gray-900">Product Indexing</h2>
          {indexingStatus && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div>
                  <p className="text-sm text-gray-500">Status</p>
                  <p className="font-semibold capitalize flex items-center gap-2">
                    {indexingStatus.status === 'running' && (
                      <RefreshCw className="w-4 h-4 animate-spin text-blue-600" />
                    )}
                    {indexingStatus.status}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Processed</p>
                  <p className="font-semibold">{indexingStatus.processed} / {indexingStatus.total}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Started</p>
                  <p className="font-semibold">{indexingStatus.started_at ? new Date(indexingStatus.started_at).toLocaleString() : 'N/A'}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Completed</p>
                  <p className="font-semibold">{indexingStatus.completed_at ? new Date(indexingStatus.completed_at).toLocaleString() : 'N/A'}</p>
                </div>
              </div>

              {(indexingStatus.status === 'running' || indexingStatus.status === 'completed') &&
                indexingStatus.total > 0 && (
                  <div className="mb-4">
                    <div className="w-full bg-gray-200 rounded-full h-2.5">
                      <div
                        className={`h-2.5 rounded-full transition-all duration-300 ${
                          indexingStatus.status === 'completed' ? 'bg-green-600' : 'bg-blue-600'
                        }`}
                        style={{
                          width: `${Math.min(
                            100,
                            Math.round((indexingStatus.processed / indexingStatus.total) * 100)
                          )}%`,
                        }}
                      />
                    </div>
                  </div>
                )}

              {indexingStatus.status === 'error' && indexingStatus.error_message && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                  {indexingStatus.error_message}
                </div>
              )}
            </>
          )}
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={() => handleStartIndexing(false)}
              disabled={indexingStatus?.status === 'running'}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Full Reindex
            </button>
            <button
              onClick={() => handleStartIndexing(true)}
              disabled={indexingStatus?.status === 'running'}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Incremental Index
            </button>
            <label className="flex items-center gap-2 px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 cursor-pointer transition-colors">
              <Upload className="w-4 h-4" />
              Import File
              <input type="file" accept=".json,.csv" onChange={handleFileUpload} className="hidden" />
            </label>
          </div>
        </div>

        {/* Settings Tabs */}
        <div className="bg-white rounded-lg shadow">
          <div className="border-b border-gray-200">
            <nav className="flex gap-4 px-6">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-2 px-4 py-4 border-b-2 transition-colors ${
                      activeTab === tab.id
                        ? 'border-blue-600 text-blue-600'
                        : 'border-transparent text-gray-600 hover:text-gray-900'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                    {tab.label}
                  </button>
                );
              })}
            </nav>
          </div>

          <div className="p-6">
            {activeTab === 'mistral' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">API Key</label>
                  <input
                    type="password"
                    value={settings.mistral.api_key}
                    onChange={(e) => updateSetting('mistral', 'api_key', e.target.value)}
                    placeholder={settings.mistral.api_key_set ? '•••••••• key configured — leave blank to keep' : 'Enter your Mistral API key'}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    {settings.mistral.api_key_set
                      ? 'A key is stored (encrypted) and never shown. Enter a new value only to replace it.'
                      : 'No key configured yet.'}
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
                  <select
                    value={settings.mistral.model}
                    onChange={(e) => updateSetting('mistral', 'model', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="mistral-large-latest">Mistral Large</option>
                    <option value="mistral-medium-latest">Mistral Medium</option>
                    <option value="mistral-small-latest">Mistral Small</option>
                    <option value="open-mistral-7b">Open Mistral 7B</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Temperature: {settings.mistral.temperature}</label>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={settings.mistral.temperature}
                    onChange={(e) => updateSetting('mistral', 'temperature', parseFloat(e.target.value))}
                    className="w-full"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Max Tokens</label>
                  <input
                    type="number"
                    value={settings.mistral.max_tokens}
                    onChange={(e) => updateSetting('mistral', 'max_tokens', parseInt(e.target.value))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
            )}

            {activeTab === 'qdrant' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Qdrant URL</label>
                  <input
                    type="text"
                    value={settings.qdrant.url}
                    onChange={(e) => updateSetting('qdrant', 'url', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Collection Name</label>
                  <input
                    type="text"
                    value={settings.qdrant.collection_name}
                    onChange={(e) => updateSetting('qdrant', 'collection_name', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Embedding Model</label>
                  <input
                    type="text"
                    value={settings.qdrant.embedding_model}
                    onChange={(e) => updateSetting('qdrant', 'embedding_model', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
            )}

            {activeTab === 'retrieval' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Number of Retrieved Documents</label>
                  <input
                    type="number"
                    value={settings.retrieval.num_retrieved}
                    onChange={(e) => updateSetting('retrieval', 'num_retrieved', parseInt(e.target.value))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Similarity Threshold: {settings.retrieval.similarity_threshold}</label>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={settings.retrieval.similarity_threshold}
                    onChange={(e) => updateSetting('retrieval', 'similarity_threshold', parseFloat(e.target.value))}
                    className="w-full"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="hybrid"
                    checked={settings.retrieval.enable_hybrid_search}
                    onChange={(e) => updateSetting('retrieval', 'enable_hybrid_search', e.target.checked)}
                    className="w-4 h-4 text-blue-600 rounded"
                  />
                  <label htmlFor="hybrid" className="text-sm font-medium text-gray-700">Enable Hybrid Search</label>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="filters"
                    checked={settings.retrieval.enable_metadata_filters}
                    onChange={(e) => updateSetting('retrieval', 'enable_metadata_filters', e.target.checked)}
                    className="w-4 h-4 text-blue-600 rounded"
                  />
                  <label htmlFor="filters" className="text-sm font-medium text-gray-700">Enable Metadata Filters</label>
                </div>
              </div>
            )}

            {activeTab === 'output' && (
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="explanation"
                    checked={settings.output.include_explanation}
                    onChange={(e) => updateSetting('output', 'include_explanation', e.target.checked)}
                    className="w-4 h-4 text-blue-600 rounded"
                  />
                  <label htmlFor="explanation" className="text-sm font-medium text-gray-700">Include Explanation Text</label>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="confidence"
                    checked={settings.output.include_confidence}
                    onChange={(e) => updateSetting('output', 'include_confidence', e.target.checked)}
                    className="w-4 h-4 text-blue-600 rounded"
                  />
                  <label htmlFor="confidence" className="text-sm font-medium text-gray-700">Include Confidence Score</label>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Number of Recommended Products</label>
                  <input
                    type="number"
                    value={settings.output.num_recommendations}
                    onChange={(e) => updateSetting('output', 'num_recommendations', parseInt(e.target.value))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="comparison"
                    checked={settings.output.include_comparison}
                    onChange={(e) => updateSetting('output', 'include_comparison', e.target.checked)}
                    className="w-4 h-4 text-blue-600 rounded"
                  />
                  <label htmlFor="comparison" className="text-sm font-medium text-gray-700">Include Comparison Table</label>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="followup"
                    checked={settings.output.include_follow_up}
                    onChange={(e) => updateSetting('output', 'include_follow_up', e.target.checked)}
                    className="w-4 h-4 text-blue-600 rounded"
                  />
                  <label htmlFor="followup" className="text-sm font-medium text-gray-700">Include Follow-up Questions</label>
                </div>
              </div>
            )}

            <div className="mt-6 pt-6 border-t border-gray-200">
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-2 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 transition-colors"
              >
                <Save className="w-4 h-4" />
                {saving ? 'Saving...' : 'Save Settings'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
