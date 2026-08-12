import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const chatAPI = {
  sendMessage: async (
    message: string,
    history: { role: string; content: string }[] = [],
    isRefinement = false
  ) => {
    const response = await api.post('/chat', {
      message,
      history,
      is_refinement: isRefinement,
    });
    return response.data;
  },

  sendFeedback: async (interactionId: number, rating: 'up' | 'down' | 'none') => {
    const response = await api.post('/chat/feedback', {
      interaction_id: interactionId,
      rating,
    });
    return response.data;
  },

  getInteractions: async (limit = 200) => {
    const response = await api.get('/chat/interactions', { params: { limit } });
    return response.data;
  },
};

export const indexingAPI = {
  getStatus: async () => {
    const response = await api.get('/index/status');
    return response.data;
  },

  startIndexing: async (incremental = false) => {
    const response = await api.post('/index/start', null, {
      params: { incremental },
    });
    return response.data;
  },

  importProducts: async (products: any[]) => {
    const response = await api.post('/index/import', { products });
    return response.data;
  },

  importFile: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/index/import/file', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
};

export const settingsAPI = {
  getSettings: async () => {
    const response = await api.get('/settings');
    return response.data;
  },

  updateSettings: async (settings: any) => {
    const response = await api.post('/settings', settings);
    return response.data;
  },

  getCategorySettings: async (category: string) => {
    const response = await api.get(`/settings/${category}`);
    return response.data;
  },

  updateCategorySettings: async (category: string, settings: any) => {
    const response = await api.post(`/settings/${category}`, { category, settings });
    return response.data;
  },
};

export const testAPI = {
  testRetrieval: async (query: string, limit = 10, scoreThreshold = 0.0) => {
    const response = await api.post('/test/retrieval', {
      query,
      limit,
      score_threshold: scoreThreshold,
    });
    return response.data;
  },
};

export const suggestionsAPI = {
  get: async (category?: string): Promise<string[]> => {
    const response = await api.get('/suggestions', {
      params: category ? { category } : {},
    });
    return response.data.suggestions || [];
  },
};

export interface ProductFilters {
  search?: string;
  category?: string;
  brand?: string;
  source?: string;
  indexed?: boolean;
  min_price?: number;
  max_price?: number;
  limit?: number;
  offset?: number;
}

export const productsAPI = {
  list: async (params: ProductFilters = {}) => {
    // Drop empty values so they aren't sent as "undefined".
    const clean = Object.fromEntries(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== '' && v !== null)
    );
    const response = await api.get('/products', { params: clean });
    return response.data as {
      total: number;
      limit: number;
      offset: number;
      products: any[];
    };
  },

  categories: async () => {
    const response = await api.get('/categories');
    return response.data as { categories: { name: string; count: number }[]; total: number };
  },

  facets: async () => {
    const response = await api.get('/facets');
    return response.data as {
      total: number;
      indexed: number;
      not_indexed: number;
      groups: Record<string, { value: string; count: number }[]>;
      price: { stats: any; buckets: { range: string; count: number }[] };
      attributes: { key: string; count: number; top_values: { value: string; count: number }[] }[];
    };
  },
};

export const syncAPI = {
  getStatus: async () => {
    const response = await api.get('/sync/status');
    return response.data;
  },

  // maxProducts: 0 = full catalog, or cap it for a quick/cheap test run.
  run: async (maxProducts = 0) => {
    const response = await api.post('/sync/run', null, {
      params: { max_products: maxProducts },
    });
    return response.data;
  },
};

export default api;
