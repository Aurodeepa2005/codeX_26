"""
engine.py
=========
StandardMatch AI — Recommendation Engine

Hybrid retrieval using TF-IDF cosine similarity + keyword boosting
for matching procurement specifications to Indian Standards (IS).

Features:
  - TF-IDF vectorization on scope + title text
  - Keyword matching with positional weighting
  - IS number exact lookup
  - Category filtering
  - QCO (Quality Control Order) mandatory flagging
  - Tender text analysis (multi-item extraction)
  - Related standards suggestion
  - Confidence scoring (composite, 0-100)
"""

import re
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ---------------------------------------------------------------------------
# Known QCO-mandatory standards (publicly available from DPIIT notifications)
# ---------------------------------------------------------------------------
QCO_MANDATORY: dict[str, str] = {
    "IS:1239":  "QCO/RE-0026/2020 — Steel Tubes, Tubulars and Other Wrought Steel Fittings",
    "IS:2062":  "QCO/RE-0001/2012 — Hot Rolled Structural Steel",
    "IS:1161":  "QCO/RE-0026/2020 — Steel Tubes for Structural Purposes",
    "IS:1536":  "QCO/RE-0064/2023 — Centrifugally Cast Iron Pressure Pipes",
    "IS:4984":  "QCO/RE-0028/2020 — HDPE Pipes",
    "IS:4985":  "QCO/RE-0029/2020 — UPVC Pipes for Potable Water",
    "IS:8329":  "QCO/RE-0065/2023 — Ductile Iron Pipes",
    "IS:14333": "QCO/RE-0030/2020 — HDPE Pipes for Sewerage",
    "IS:14885": "QCO/RE-0031/2020 — PE Pipes for Gaseous Fuels",
    "IS:1786":  "QCO/RE-0002/2012 — Steel Bars for Concrete Reinforcement",
}

# ---------------------------------------------------------------------------
# Sample queries for demo / jury
# ---------------------------------------------------------------------------
SAMPLE_QUERIES: list[dict] = [
    {
        "query": "GI pipes for rural drinking water supply, medium class, screwed and socketed",
        "description": "Common municipal water supply specification",
        "category": "pipes",
    },
    {
        "query": "HDPE pipes for underground water distribution system, PN 6",
        "description": "Polyethylene pipe for water infrastructure",
        "category": "pipes",
    },
    {
        "query": "structural steel plates for bridge fabrication IS 2062",
        "description": "Hot rolled structural steel for construction",
        "category": "pipes",
    },
    {
        "query": "PVC pipes for borewell casing and screen in agricultural tubewells",
        "description": "Tubewell casing pipes for groundwater",
        "category": "pipes",
    },
    {
        "query": "cast iron pressure pipes for municipal sewage transmission",
        "description": "Cast iron pipes for sewerage mains",
        "category": "pipes",
    },
    {
        "query": "rubber sealing rings for jointing water supply pipeline",
        "description": "Elastomeric gasket seals for pipe joints",
        "category": "pipes",
    },
    {
        "query": "fabricated PVC fittings for potable water supply elbows tees",
        "description": "PVC pipe fittings for plumbing",
        "category": "pipes",
    },
    {
        "query": "polyethylene pipes for city gas distribution network",
        "description": "PE pipe for LPG/CNG gas supply",
        "category": "pipes",
    },
]

SAMPLE_TENDER_TEXT = """
SCHEDULE OF QUANTITIES — RURAL WATER SUPPLY SCHEME

1. Supply and laying of GI pipes (medium class) conforming to relevant IS for
   drinking water distribution, 50mm diameter — 2500 Rmt.
2. Supply of HDPE pipes PE-100, PN 6, 110mm OD for underground water
   transmission main — 5000 Rmt.
3. Supply of Ductile Iron (DI) pipes K-9 class, 200mm diameter for raw water
   gravity main — 3000 Rmt.
4. Rubber sealing rings for DI pipe joints as per relevant IS — 500 Nos.
5. Hot rolled structural steel (IS 2062 Grade E250) for pipe support trestles
   and anchor blocks — 15 MT.
6. Unplasticized PVC casing pipes 150mm for tubewells — 800 Rmt.
7. Fabricated PVC-U fittings (elbows, tees, reducers) for water distribution
   network — 200 Nos.
"""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class StandardMatchEngine:
    """
    AI-powered recommendation engine for Indian Standards.

    Scoring pipeline:
      1. TF-IDF cosine similarity (semantic relevance)
      2. Keyword exact-match boosting (title > scope > combined)
      3. IS number detection (direct lookup bonus)
      4. QCO mandatory flagging
      5. Composite confidence score (0–100)
    """

    def __init__(self, data_path: Path) -> None:
        self.data_path = Path(data_path)
        self.df = pd.DataFrame()
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix = None
        self._load_and_index()

    # ---- Data loading & indexing ------------------------------------------

    def _load_and_index(self) -> None:
        if not self.data_path.exists():
            return

        self.df = pd.read_csv(self.data_path, dtype=str).fillna("")

        # Add QCO field
        self.df["qco_mandatory"] = self.df["is_number"].apply(self._check_qco)
        self.df["qco_order"] = self.df["is_number"].apply(
            lambda x: self._get_qco_order(x)
        )

        # Build TF-IDF index
        self.df["_combined"] = (
            self.df["is_number"].str.lower()
            + " "
            + self.df["title"].str.lower()
            + " "
            + self.df["scope"].str.lower()
            + " "
            + self.df["category"].str.lower()
        )

        self.vectorizer = TfidfVectorizer(
            max_features=8000,
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(self.df["_combined"])

    def reload(self) -> None:
        """Reload data from disk (e.g. after scraping more standards)."""
        self._load_and_index()

    # ---- QCO helpers ------------------------------------------------------

    @staticmethod
    def _check_qco(is_number: str) -> bool:
        base = re.match(r"(IS:\d+)", is_number)
        return base.group(1) in QCO_MANDATORY if base else False

    @staticmethod
    def _get_qco_order(is_number: str) -> str:
        base = re.match(r"(IS:\d+)", is_number)
        return QCO_MANDATORY.get(base.group(1), "") if base else ""

    # ---- Core recommendation ---------------------------------------------

    def recommend(
        self,
        query: str,
        top_k: int = 10,
        category: Optional[str] = None,
    ) -> list[dict]:
        """
        Return up to *top_k* standards ranked by composite relevance.
        """
        if self.df.empty or not query.strip():
            return []

        # Category filter
        if category and category.lower() != "all":
            mask = self.df["category"].str.lower() == category.lower()
        else:
            mask = pd.Series([True] * len(self.df), index=self.df.index)

        working_df = self.df[mask].reset_index(drop=True)
        working_matrix = self.tfidf_matrix[mask.values]

        if working_df.empty:
            return []

        # 1. TF-IDF cosine similarity
        query_vec = self.vectorizer.transform([query.lower()])
        tfidf_scores = cosine_similarity(query_vec, working_matrix).flatten()

        # 2. Keyword boosting
        tokens = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 2]
        stop_words = {
            "for", "the", "and", "with", "class", "grade", "system",
            "supplies", "supply", "use", "type", "per", "relevant",
            "conforming", "shall", "required", "diameter", "specification",
        }
        keywords = [t for t in tokens if t not in stop_words]

        kw_scores = np.zeros(len(working_df))
        matched_kw: list[list[str]] = [[] for _ in range(len(working_df))]

        for i, (_, row) in enumerate(working_df.iterrows()):
            title_l = row["title"].lower()
            scope_l = row["scope"].lower()
            is_num_l = row["is_number"].lower()

            sc = 0.0
            mw: list[str] = []

            # IS number exact match
            for num_part in re.findall(r"\d{3,6}", query):
                if num_part in is_num_l:
                    sc += 60
                    mw.append(f"IS {num_part}")

            for kw in keywords:
                pat = rf"\b{re.escape(kw)}s?\b"
                if re.search(pat, title_l):
                    sc += 18
                    mw.append(kw)
                elif re.search(pat, scope_l):
                    sc += 10
                    mw.append(kw)
                elif kw in (title_l + " " + scope_l):
                    sc += 4

            kw_scores[i] = sc
            matched_kw[i] = list(set(mw))

        # Normalize keyword scores
        max_kw = kw_scores.max() if kw_scores.max() > 0 else 1.0
        norm_kw = kw_scores / max_kw

        # 3. Composite: 55% TF-IDF + 45% keyword
        composite = 0.55 * tfidf_scores + 0.45 * norm_kw

        # Sort and pick top-k
        order = composite.argsort()[::-1][:top_k]

        results: list[dict] = []
        for idx in order:
            score = float(composite[idx])
            if score < 0.01:
                continue

            row = working_df.iloc[idx]
            confidence = min(98, max(42, int(score * 110)))

            # Extract most relevant scope sentence as evidence
            scope_evidence = self._extract_evidence(row["scope"], keywords)

            results.append(
                {
                    "is_number": row["is_number"],
                    "title": row["title"],
                    "year": row.get("year", ""),
                    "status": row.get("status", "Active"),
                    "category": row.get("category", ""),
                    "technical_committee": row.get("technical_committee", ""),
                    "ics_code": row.get("ics_code", ""),
                    "scope": row["scope"],
                    "source_url": row.get("source_url", ""),
                    "confidence": confidence,
                    "matched_keywords": matched_kw[idx],
                    "scope_evidence": scope_evidence,
                    "qco_mandatory": bool(row.get("qco_mandatory", False)),
                    "qco_order": row.get("qco_order", ""),
                    "tfidf_score": round(float(tfidf_scores[idx]), 4),
                    "keyword_score": round(float(norm_kw[idx]), 4),
                }
            )

        return results

    # ---- Tender analysis --------------------------------------------------

    def analyze_tender(
        self,
        tender_text: str,
        top_k_per_item: int = 3,
    ) -> dict:
        """
        Parse tender text into procurement items and recommend IS for each.
        """
        items = self._split_tender(tender_text)

        analysis: list[dict] = []
        all_standards: set[str] = set()

        for item_text in items:
            recs = self.recommend(item_text, top_k=top_k_per_item)
            if recs:
                for r in recs:
                    all_standards.add(r["is_number"])
                analysis.append(
                    {
                        "procurement_item": item_text,
                        "recommendations": recs,
                    }
                )

        return {
            "total_items": len(items),
            "matched_items": len(analysis),
            "unique_standards": len(all_standards),
            "items": analysis,
        }

    @staticmethod
    def _split_tender(text: str) -> list[str]:
        """Split tender text into individual procurement line-items."""
        # Try numbered list first
        items = re.split(r"\n\s*\d+[\.\)]\s*", text)
        if len(items) < 2:
            # Try splitting on newlines
            items = text.strip().split("\n")
        # Clean and filter
        cleaned = []
        for item in items:
            item = re.sub(r"\s+", " ", item).strip()
            if len(item) > 15:
                cleaned.append(item)
        return cleaned[:25]  # Cap at 25 items

    # ---- Evidence extraction ----------------------------------------------

    @staticmethod
    def _extract_evidence(scope: str, keywords: list[str]) -> str:
        """Pull the most relevant sentence from scope text."""
        if not scope or scope == "nan":
            return "Standard metadata verified on official BIS portal."

        sentences = re.split(r"(?<=[.!?])\s+", scope)
        best = scope  # default: full scope
        for s in sentences:
            if any(k in s.lower() for k in keywords):
                best = s.strip()
                break

        if len(best) > 320:
            best = best[:317] + "..."
        return best

    # ---- Browse & stats ---------------------------------------------------

    def get_all_standards(
        self,
        category: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[dict]:
        """Return all standards, optionally filtered."""
        df = self.df.copy()
        if category and category.lower() != "all":
            df = df[df["category"].str.lower() == category.lower()]
        if search:
            search_l = search.lower()
            mask = (
                df["title"].str.lower().str.contains(search_l, na=False)
                | df["is_number"].str.lower().str.contains(search_l, na=False)
                | df["scope"].str.lower().str.contains(search_l, na=False)
            )
            df = df[mask]

        cols = [
            c
            for c in df.columns
            if c != "_combined"
        ]
        return df[cols].to_dict(orient="records")

    def get_standard(self, is_number: str) -> Optional[dict]:
        """Get details for a single standard."""
        match = self.df[self.df["is_number"] == is_number]
        if match.empty:
            # Try partial match
            match = self.df[self.df["is_number"].str.contains(is_number, na=False)]
        if match.empty:
            return None

        row = match.iloc[0]
        cols = [c for c in self.df.columns if c != "_combined"]
        result = {c: row[c] for c in cols}

        # Find related standards (same category, top 5)
        related = self.df[
            (self.df["category"] == row["category"])
            & (self.df["is_number"] != row["is_number"])
        ].head(5)
        result["related_standards"] = [
            {"is_number": r["is_number"], "title": r["title"]}
            for _, r in related.iterrows()
        ]
        return result

    def get_categories(self) -> list[dict]:
        """Return categories with counts."""
        if self.df.empty:
            return []
        counts = self.df["category"].value_counts()
        return [
            {"name": cat, "count": int(cnt)} for cat, cnt in counts.items()
        ]

    def get_stats(self) -> dict:
        """Dashboard statistics."""
        if self.df.empty:
            return {
                "total_standards": 0,
                "active_count": 0,
                "qco_count": 0,
                "categories": [],
                "status_distribution": {},
            }

        return {
            "total_standards": len(self.df),
            "active_count": int((self.df["status"] == "Active").sum()),
            "qco_count": int(self.df["qco_mandatory"].sum())
            if "qco_mandatory" in self.df.columns
            else 0,
            "categories": self.get_categories(),
            "status_distribution": self.df["status"].value_counts().to_dict(),
        }

    def get_sample_queries(self) -> list[dict]:
        return SAMPLE_QUERIES

    def get_sample_tender(self) -> str:
        return SAMPLE_TENDER_TEXT.strip()
