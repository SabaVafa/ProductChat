# ProductChat - AI Product Recommendation Assistant

A complete RAG-based product recommendation system with Mistral AI integration.

## Features

- **Product Indexing**: Import and index products from various sources (JSON, CSV, database)
- **RAG Chat Engine**: AI-powered product recommendations using vector search
- **Admin Settings**: Configure Mistral AI, vector database, and retrieval parameters
- **Testing Interface**: Built-in chat UI for testing recommendations
- **REST API**: External API for integration with other frontends

## Tech Stack

### Backend

- Python 3.12
- FastAPI
- SQLAlchemy
- Pydantic
- LangChain
- Qdrant (Vector Database)
- PostgreSQL
- Mistral AI

### Frontend

- React 18
- TypeScript
- Tailwind CSS
- Vite

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.12 (for local development)
- Node.js 18+ (for local development)

### Using Docker (Recommended)

```bash
# Clone and navigate to the project
cd ProductChat

# Start all services
docker-compose up -d

# The application will be available at:
# - Frontend: http://localhost:80
# - Backend API: http://localhost:8000
# - API Docs: http://localhost:8000/docs
```

### Local Development

#### Backend Setup

```bash
cd backend

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your configuration

# Run database migrations
alembic upgrade head

# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

## Configuration

### Environment Variables

Create a `.env` file in the backend directory:

```env
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/productchat
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=productchat

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_NAME=products

# Mistral AI (configure via UI or set defaults)
MISTRAL_API_KEY=your_api_key_here
MISTRAL_MODEL=mistral-large-latest
MISTRAL_TEMPERATURE=0.7
MISTRAL_MAX_TOKENS=1000

# Security
SECRET_KEY=your-secret-key-here
ENCRYPTION_KEY=your-32-byte-encryption-key

# Application
API_PREFIX=/api
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

## API Endpoints

### Chat

```bash
POST /api/chat
{
  "message": "I need a laptop for programming"
}

Response:
{
  "answer": "Based on your needs...",
  "products": [
    {
      "id": "123",
      "name": "Laptop X",
      "price": 1200,
      "image": "url",
      "reason": "Best for programming"
    }
  ]
}
```

### Indexing

```bash
POST /api/index/start
GET /api/index/status
```

### Settings

```bash
GET /api/settings
POST /api/settings
```

### Testing

```bash
POST /api/test/retrieval
{
  "query": "laptop for programming"
}
```

## Example Product Data

Example product dataset is provided in `data/example_products.json`.

Import it via the admin UI or API:

```bash
curl -X POST http://localhost:8000/api/index/import \
  -H "Content-Type: application/json" \
  -d @data/example_products.json
```

## Project Structure

```
ProductChat/
├── backend/
│   ├── app/
│   │   ├── api/          # API endpoints
│   │   ├── models/       # Database models
│   │   ├── services/     # Business logic
│   │   ├── database/     # Database configuration
│   │   ├── schemas/      # Pydantic schemas
│   │   └── main.py       # FastAPI app
│   ├── alembic/          # Database migrations
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/   # React components
│   │   ├── pages/        # Page components
│   │   ├── services/     # API services
│   │   └── types/        # TypeScript types
│   └── package.json
├── data/                 # Example data
├── docker-compose.yml
└── Dockerfile
```

## Security Features

- API token encryption in database
- Input validation with Pydantic
- Rate limiting
- Comprehensive logging
- Error handling
- CORS configuration

## License

MIT
