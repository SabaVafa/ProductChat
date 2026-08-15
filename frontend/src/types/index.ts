export interface ProductCard {
  id: string;
  name: string;
  price?: number;
  image?: string;
  url?: string;
  reason: string;
  score?: number;
}

export interface RagDebugStep {
  step: string;
  [key: string]: any;
}

export interface RagDebug {
  query: string;
  embedding_model?: string;
  steps: RagDebugStep[];
}

export interface ChatResponse {
  answer: string;
  products: ProductCard[];
  follow_up_question?: string;
  refine_suggestions?: string[];
  interaction_id?: number;
  debug?: RagDebug;
}

export interface ChatRequest {
  message: string;
}

export interface IndexingStatus {
  status: string;
  processed: number;
  total: number;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
}

export interface Settings {
  mistral: {
    api_key: string;
    api_key_set?: boolean;
    model: string;
    temperature: number;
    max_tokens: number;
  };
  qdrant: {
    url: string;
    collection_name: string;
    embedding_model: string;
  };
  retrieval: {
    num_retrieved: number;
    similarity_threshold: number;
    enable_hybrid_search: boolean;
    enable_metadata_filters: boolean;
  };
  output: {
    include_explanation: boolean;
    include_confidence: boolean;
    num_recommendations: number;
    include_comparison: boolean;
    include_follow_up: boolean;
  };
  product_data: {
    database_connection: string;
    import_format: string;
    field_mapping: string;
  };
}
