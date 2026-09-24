# HTH 2.0 - AI Data Analyst

An intelligent data analysis platform featuring an automated ingestion and profiling pipeline, natural language query parsing, semantic schema mapping, and deterministic query execution.

---

## 📌 Project Overview

**HTH 2.0** empowers users to upload diverse datasets (CSV, Excel) and extract meaningful analytical insights through natural language questions. The system combines robust data cleaning, schema inference, semantic column resolution, and a deterministic query engine to deliver precise answers without hallucination.

```
                  ┌────────────────────────┐
                  │ Natural Language Query │
                  └───────────┬────────────┘
                              │
                              ▼
                  ┌────────────────────────┐
                  │    question_parser     │
                  └───────────┬────────────┘
                              │
                              ▼
                  ┌────────────────────────┐
                  │       Query Plan       │
                  └───────────┬────────────┘
                              │
                              ▼
                  ┌────────────────────────┐
                  │     schema_mapper      │
                  └───────────┬────────────┘
                              │
                              ▼
                  ┌────────────────────────┐
                  │    query_validator     │
                  └───────────┬────────────┘
                              │
                              ▼
                  ┌────────────────────────┐
                  │     query_executor     │
                  └───────────┬────────────┘
                              │
                              ▼
                  ┌────────────────────────┐
                  │   Pandas Execution     │
                  └───────────┬────────────┘
                              │
                              ▼
                  ┌────────────────────────┐
                  │      Final Result      │
                  └────────────────────────┘
```

---

## 📁 Repository Structure

```
HTH2.0/
├── backend/
│   ├── analyst/                  # Natural language query engine & execution
│   │   ├── __init__.py
│   │   ├── query_planner.py      # Query plan definition & structure validation
│   │   ├── question_parser.py    # Intent, metric, group-by, and filter extraction
│   │   ├── schema_mapper.py      # Exact & semantic column mapping, metric derivation
│   │   ├── query_validator.py    # Query plan validation against dataset schemas
│   │   ├── query_executor.py     # Deterministic query execution engine (Pandas)
│   │   └── test_queries.py       # Query regression suite
│   ├── file_processing/          # Data ingestion & cleaning pipeline
│   │   ├── __init__.py
│   │   ├── file_loader.py        # File loader for CSV and Excel formats
│   │   ├── schema_inference.py   # Type inference & schema detection
│   │   ├── data_profiler.py      # Dataset profiling, statistics, and distributions
│   │   ├── data_cleaner.py       # Missing values, normalization, formatting
│   │   └── pipeline.py           # End-to-end ingestion pipeline
│   ├── routes/
│   │   └── upload.py             # File upload and processing API endpoints
│   ├── uploads/                  # Temporary upload storage
│   ├── main.py                   # FastAPI application entry point
│   └── requirements.txt          # Backend dependencies
├── frontend/                     # React + Vite frontend interface
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── vite.config.js
└── README.md
```

---

## 🧠 Analyst / Query Engine Architecture

The Analyst module translates natural language business questions into deterministic execution plans:

### 1. Question Parser (`question_parser.py`)
- Extracts analytical operations: `sum`, `average`, `count`, `count_distinct`, `min`, `max`.
- Detects metrics (e.g., `revenue`, `profit`, `quantity`, `unit_price`, `discount`).
- Detects group-by dimensions (e.g., `product`, `category`, `customer`, `country`, `state`, `region`).
- Detects filters, comparative operators (`=`, `!=`, `>`, `<`, `>=`, `<=`), and top/bottom `N` limits.

**Example Query Plan Output:**
```python
{
    "operation": "sum",
    "metric": "revenue",
    "group_by": "product",
    "filters": [],
    "sort": "desc",
    "limit": 5
}
```

### 2. Schema Mapper (`schema_mapper.py`)
- Maps business concepts to actual dataset columns using exact rules and semantic cosine similarity.
- Handles cross-dataset metric derivation:
  - **Direct Metric:** e.g., Superstore dataset maps `revenue` ➔ `Sales`.
  - **Derived Metric:** e.g., Online Retail II dataset derives `revenue` ➔ `Quantity * Price`.

### 3. Query Validator (`query_validator.py`)
- Verifies that operations, metrics, dimensions, and filter columns exist in the active dataset schema before execution.

### 4. Query Executor (`query_executor.py`)
- Applies filters, executes groupings, aggregations, sorts, and limits using Pandas DataFrames.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+ (tested with Python 3.12)
- Node.js 18+ & npm

### 1. Backend Setup

```bash
# Navigate to the backend directory
cd backend

# Create and activate a virtual environment
python -m venv venv
# Windows (PowerShell):
venv\Scripts\Activate.ps1
# Linux/macOS:
# source venv/bin/activate

# Install core backend dependencies
pip install -r requirements.txt

# Install Analyst module dependencies
pip install numpy scikit-learn sentence-transformers duckdb
```

#### Run Backend Server
```bash
python main.py
```
The FastAPI backend will start at `http://127.0.0.1:8000`.
- API Documentation (Swagger UI): `http://127.0.0.1:8000/docs`

### 2. Frontend Setup

```bash
# Navigate to the frontend directory
cd frontend

# Install dependencies
npm install

# Start Vite development server
npm run dev
```
The frontend will start at `http://localhost:5173`.

---

## 🧪 Verification & Testing

### Analyst Syntax Check
```bash
python -m compileall backend/analyst
```

### Question Parser Import & Plan Verification
```bash
python -c "from backend.analyst.question_parser import parse_question; print(parse_question('What are the top 5 products by revenue?'))"
```

---

## 📄 License
This project is part of HTH 2.0. All rights reserved.
