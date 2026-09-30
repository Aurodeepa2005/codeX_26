"""
server.py
=========
StandardMatch AI — FastAPI Backend

REST API for the recommendation engine + static frontend serving.

Endpoints:
  GET  /                        → Main web interface
  GET  /api/stats               → Dashboard statistics
  GET  /api/categories          → Category list with counts
  GET  /api/standards           → Browse all standards (query params: category, search)
  GET  /api/standards/{is_no}   → Single standard detail
  POST /api/recommend           → Get IS recommendations for a query
  POST /api/analyze-tender      → Bulk tender text analysis
  GET  /api/sample-queries      → Sample demo queries
  GET  /api/sample-tender       → Sample tender text for demo
  POST /api/reload              → Reload dataset from disk
"""

import sys
from pathlib import Path

# Ensure UTF-8 stdout on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_PATH = PROJECT_ROOT / "data" / "processed" / "standards.csv"
STATIC_DIR = PROJECT_ROOT / "static"

# ---------------------------------------------------------------------------
# Engine initialization
# ---------------------------------------------------------------------------
sys.path.insert(0, str(PROJECT_ROOT))
from src.retrieval.engine import StandardMatchEngine

engine = StandardMatchEngine(DATA_PATH)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="StandardMatch AI",
    description=(
        "AI-Powered Recommendation Engine for Identifying Applicable "
        "Indian Standards (IS) for Procurement Specifications"
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (CSS, JS, images)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "css").mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "js").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class RecommendRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Procurement specification text")
    top_k: int = Field(10, ge=1, le=50, description="Max results to return")
    category: str | None = Field(None, description="Filter by category")


class TenderRequest(BaseModel):
    tender_text: str = Field(..., min_length=10, description="Tender document text")
    top_k_per_item: int = Field(3, ge=1, le=10, description="Results per item")


# ---------------------------------------------------------------------------
# Routes — Frontend
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file), media_type="text/html")
    return HTMLResponse("<h1>StandardMatch AI — Frontend not found</h1>")


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------
@app.get("/api/stats")
async def get_stats():
    return engine.get_stats()


@app.get("/api/categories")
async def get_categories():
    return engine.get_categories()


@app.get("/api/standards")
async def get_standards(
    category: str | None = Query(None),
    search: str | None = Query(None),
):
    return engine.get_all_standards(category=category, search=search)


@app.get("/api/standards/{is_number:path}")
async def get_standard(is_number: str):
    result = engine.get_standard(is_number)
    if result is None:
        return {"error": f"Standard '{is_number}' not found"}
    return result


@app.post("/api/recommend")
async def recommend(req: RecommendRequest):
    results = engine.recommend(
        query=req.query,
        top_k=req.top_k,
        category=req.category,
    )
    return {
        "query": req.query,
        "total_results": len(results),
        "results": results,
    }


@app.post("/api/analyze-tender")
async def analyze_tender(req: TenderRequest):
    return engine.analyze_tender(
        tender_text=req.tender_text,
        top_k_per_item=req.top_k_per_item,
    )


@app.get("/api/sample-queries")
async def sample_queries():
    return engine.get_sample_queries()


@app.get("/api/sample-tender")
async def sample_tender():
    return {"text": engine.get_sample_tender()}


@app.post("/api/reload")
async def reload_data():
    engine.reload()
    return {"status": "ok", "total_standards": len(engine.df)}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    print("\n" + "=" * 60)
    print("  STANDARDMATCH AI — Server")
    print(f"  Standards loaded: {len(engine.df)}")
    print(f"  Data path:        {DATA_PATH}")
    print("=" * 60 + "\n")

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
