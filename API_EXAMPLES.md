# API Examples

This document provides example API calls for the ProductChat backend.

## Base URL
- Local: `http://localhost:8000`
- Docker: `http://localhost:8000`

## Chat API

### Send a message
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I need a laptop for programming under $1500"
  }'
```

### Response
```json
{
  "answer": "Based on your requirements for programming under $1500, I recommend the following laptops...",
  "products": [
    {
      "id": "laptop-003",
      "name": "Lenovo ThinkPad X1 Carbon",
      "price": 1299.0,
      "image": "https://images.unsplash.com/...",
      "reason": "Excellent keyboard and lightweight design perfect for developers",
      "score": 0.95
    }
  ],
  "follow_up_question": "Do you prefer Windows or macOS?"
}
```

## Indexing API

### Get indexing status
```bash
curl http://localhost:8000/api/index/status
```

### Response
```json
{
  "status": "completed",
  "processed": 15,
  "total": 15,
  "error_message": null,
  "started_at": "2024-01-15T10:00:00Z",
  "completed_at": "2024-01-15T10:05:00Z"
}
```

### Start full indexing
```bash
curl -X POST http://localhost:8000/api/index/start
```

### Start incremental indexing
```bash
curl -X POST "http://localhost:8000/api/index/start?incremental=true"
```

### Import products from JSON
```bash
curl -X POST http://localhost:8000/api/index/import \
  -H "Content-Type: application/json" \
  -d @data/example_products.json
```

### Import products from file
```bash
curl -X POST http://localhost:8000/api/index/import/file \
  -F "file=@data/example_products.json"
```

## Settings API

### Get all settings
```bash
curl http://localhost:8000/api/settings
```

### Response
```json
{
  "mistral": {
    "api_key": "encrypted_key",
    "model": "mistral-large-latest",
    "temperature": 0.7,
    "max_tokens": 1000
  },
  "qdrant": {
    "url": "http://localhost:6333",
    "collection_name": "products",
    "embedding_model": "mistral-embed"
  },
  "retrieval": {
    "num_retrieved": 10,
    "similarity_threshold": 0.0,
    "enable_hybrid_search": false,
    "enable_metadata_filters": false
  },
  "output": {
    "include_explanation": true,
    "include_confidence": false,
    "num_recommendations": 3,
    "include_comparison": false,
    "include_follow_up": false
  },
  "product_data": {
    "database_connection": "",
    "import_format": "json",
    "field_mapping": "{}"
  }
}
```

### Update settings
```bash
curl -X POST http://localhost:8000/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "mistral": {
      "api_key": "your_new_api_key",
      "model": "mistral-large-latest",
      "temperature": 0.8,
      "max_tokens": 1500
    }
  }'
```

### Get category settings
```bash
curl http://localhost:8000/api/settings/mistral
```

### Update category settings
```bash
curl -X POST http://localhost:8000/api/settings/mistral \
  -H "Content-Type: application/json" \
  -d '{
    "category": "mistral",
    "settings": {
      "api_key": "your_api_key",
      "model": "mistral-large-latest",
      "temperature": 0.7,
      "max_tokens": 1000
    }
  }'
```

## Testing API

### Test retrieval only
```bash
curl -X POST http://localhost:8000/api/test/retrieval \
  -H "Content-Type: application/json" \
  -d '{
    "query": "laptop for programming",
    "limit": 5,
    "score_threshold": 0.5
  }'
```

### Response
```json
{
  "products": [
    {
      "product_id": "laptop-001",
      "name": "MacBook Pro 14-inch",
      "description": "Apple M3 Pro chip...",
      "category": "Laptops",
      "brand": "Apple",
      "price": 1999.0,
      "image_url": "https://...",
      "attributes": {...},
      "score": 0.92
    }
  ],
  "total": 5
}
```

## Using with Python

```python
import requests

BASE_URL = "http://localhost:8000/api"

# Chat
response = requests.post(f"{BASE_URL}/chat", json={
    "message": "I need a laptop for programming"
})
print(response.json())

# Indexing
response = requests.post(f"{BASE_URL}/index/start")
print(response.json())

# Settings
response = requests.get(f"{BASE_URL}/settings")
print(response.json())
```

## Using with JavaScript/TypeScript

```typescript
import axios from 'axios';

const BASE_URL = 'http://localhost:8000/api';

// Chat
const chatResponse = await axios.post(`${BASE_URL}/chat`, {
  message: 'I need a laptop for programming'
});
console.log(chatResponse.data);

// Indexing
const indexResponse = await axios.post(`${BASE_URL}/index/start`);
console.log(indexResponse.data);

// Settings
const settingsResponse = await axios.get(`${BASE_URL}/settings`);
console.log(settingsResponse.data);
```
