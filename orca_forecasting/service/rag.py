"""ORCA RAG (Retrieval-Augmented Generation) Knowledge Base & Engine.

Indexes oceanographic and fisheries knowledge from orca_forecasting/knowledge/
and provides fast, robust semantic keyword + section retrieval for non-technical
explanations of marine metrics, algorithms, and physical phenomena.
"""

from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"


class KnowledgeChunk:
    def __init__(self, doc_name: str, section_title: str, content: str):
        self.doc_name = doc_name
        self.section_title = section_title
        self.content = content.strip()
        
        # Tokenize content and title for scoring
        text = f"{section_title} {self.content}".lower()
        self.tokens = set(re.findall(r"\b[a-z0-9_-]{2,}\b", text))
        self.token_counts = {}
        for t in re.findall(r"\b[a-z0-9_-]{2,}\b", text):
            self.token_counts[t] = self.token_counts.get(t, 0) + 1

    def score(self, query_tokens: List[str]) -> float:
        if not query_tokens:
            return 0.0
        score = 0.0
        title_lower = self.section_title.lower()
        for qt in query_tokens:
            if qt in title_lower:
                score += 5.0
            if qt in self.tokens:
                # Term frequency boost
                count = self.token_counts.get(qt, 1)
                score += 1.0 + math.log(1 + count)
        return score


class ORCAKnowledgeBase:
    """Manages document chunks and semantic retrieval over project knowledge."""

    def __init__(self, knowledge_dir: Optional[Path] = None):
        self.knowledge_dir = knowledge_dir or KNOWLEDGE_DIR
        self.chunks: List[KnowledgeChunk] = []
        self._load_documents()

    def _load_documents(self):
        self.chunks.clear()
        if not self.knowledge_dir.exists():
            return

        for md_file in self.knowledge_dir.glob("*.md"):
            doc_name = md_file.stem
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            # Split document by markdown headings (## )
            raw_sections = re.split(r"\n(?=## )", text)
            for section in raw_sections:
                lines = section.strip().split("\n")
                if not lines:
                    continue
                first_line = lines[0].strip()
                if first_line.startswith("## "):
                    title = first_line.replace("## ", "").strip()
                    body = "\n".join(lines[1:]).strip()
                elif first_line.startswith("# "):
                    title = first_line.replace("# ", "").strip()
                    body = "\n".join(lines[1:]).strip()
                else:
                    title = doc_name.replace("_", " ").title()
                    body = section.strip()

                if body:
                    self.chunks.append(KnowledgeChunk(doc_name, title, body))

    def retrieve(self, query: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """Retrieves top matching knowledge chunks for a given natural language query."""
        if not self.chunks:
            self._load_documents()

        q_tokens = [t for t in re.findall(r"\b[a-z0-9_-]{2,}\b", query.lower()) if len(t) > 1]
        scored_chunks: List[Tuple[float, KnowledgeChunk]] = []

        for chunk in self.chunks:
            s = chunk.score(q_tokens)
            if s > 0.0:
                scored_chunks.append((s, chunk))

        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        results = []
        for s, chunk in scored_chunks[:top_k]:
            results.append({
                "document": chunk.doc_name,
                "section": chunk.section_title,
                "content": chunk.content,
                "score": round(s, 2),
            })
        return results

    def get_plain_explanation(self, query: str) -> Optional[str]:
        """Provides a direct, plain-English explanation for common oceanographic queries."""
        q_lower = query.lower()

        if any(w in q_lower for w in ["what is chlorophyll", "chlorophyll mean", "chlorophyll high", "why chlorophyll"]):
            return (
                "Chlorophyll-a is the green pigment in marine phytoplankton (microscopic ocean plants). "
                "Higher concentrations (0.5 to 3.5 mg/m³) indicate an active biological forage front where "
                "zooplankton thrive, naturally attracting schooling baitfish like sardines and mackerel."
            )

        if any(w in q_lower for w in ["why is this green", "why green", "why area green"]):
            return (
                "Green on the map indicates optimal, stable ocean health (score 75 to 100). "
                "Water temperature, salinity, currents, and chlorophyll are within balanced historical ranges, "
                "creating a thriving, non-stressed habitat for marine life."
            )

        if any(w in q_lower for w in ["why is this red", "why red", "why area red"]):
            return (
                "Red on the map indicates an anomalous biophysical disturbance (score below 55). "
                "This usually flags a Marine Heatwave (abnormally hot water > +1.5°C above normal), "
                "extreme stratification, or sudden current disruption. Pelagic fish tend to avoid or dive deeper below these warm surface layers."
            )

        if any(w in q_lower for w in ["what is sst", "why sst matter", "sea temperature normal", "what is temperature"]):
            return (
                "Sea Surface Temperature (SST) is the temperature of the upper ocean layer. "
                "In the Arabian Sea, typical temperatures are 26.5°C to 30.0°C. Temperature governs fish metabolism, "
                "and sharp boundaries between warm and cooler water (thermal fronts) often trap nutrients and concentrate pelagic fish."
            )

        if any(w in q_lower for w in ["what is upwelling", "why upwelling", "upwelling mean", "upwelling important"]):
            return (
                "Upwelling is a wind-driven process where cold, deep, nutrient-rich water rises to the sunlit surface. "
                "It acts like natural fertilizer for the ocean, sparking rapid plankton growth within 24 to 72 hours "
                "and creating the richest fishing grounds in the Arabian Sea."
            )

        if any(w in q_lower for w in ["what does marine health mean", "what is marine health", "what is mhi", "marine health mean"]):
            return (
                "The Marine Health Index (MHI) is a 0 to 100 score calculated by ORCA's Isolation Forest model. "
                "Scores of 75+ mean healthy, balanced waters; 55 to 74 mean monitored or shifting waters; "
                "and scores below 55 indicate thermal stress, severe anomalies, or oxygen-poor pockets."
            )

        if any(w in q_lower for w in ["how orca calculates", "how does orca determine", "how calculate fishing suitability"]):
            return (
                "ORCA determines fishing suitability using 5 authentic physical ocean variables: "
                "ideal water temperature (25 pts), cold upwelling fronts (25 pts), phytoplankton forage density (25 pts), "
                "schooling current currents/eddies (15 pts), and overall marine habitat health (10 pts). "
                "Scores above 65/100 indicate high-probability commercial fishing zones."
            )

        if any(w in q_lower for w in ["what fish", "what species", "target catch", "fish can i expect"]):
            return (
                "ORCA models oceanographic suitability and forage fronts rather than tracking individual fish from space. "
                "However, along verified thermal and upwelling fronts in the Arabian Sea, the primary commercial pelagics "
                "are Indian Mackerel, Oil Sardines, Yellowfin Tuna, and Squid."
            )

        if any(w in q_lower for w in ["12 nm", "12 nautical", "boundary", "regulation", "territorial", "artisanal zone", "maritime zone"]):
            return (
                "Under the Maritime Zones of India Act (1976), coastal waters from 0 to 12 Nautical Miles (~22.2 km) "
                "are designated as Territorial Waters and reserved exclusively for traditional and artisanal small-scale fishers. "
                "Commercial and mechanized fishing is permitted only seaward of this 12 NM line in the Contiguous Zone and Exclusive Economic Zone (EEZ). "
                "ORCA strictly enforces this 12 NM boundary as a computational hard filter, eliminating any fishing spots within 22.2 km of the coastline."
            )

        # Fallback to general retrieval
        retrieved = self.retrieve(query, top_k=1)
        if retrieved:
            chunk = retrieved[0]
            first_para = chunk["content"].split("\n\n")[0].replace("\n", " ").strip()
            return f"According to ORCA Oceanographic Records ({chunk['section']}): {first_para}"

        return None


# Global singleton instance
_KNOWLEDGE_BASE: Optional[ORCAKnowledgeBase] = None


def get_knowledge_base() -> ORCAKnowledgeBase:
    global _KNOWLEDGE_BASE
    if _KNOWLEDGE_BASE is None:
        _KNOWLEDGE_BASE = ORCAKnowledgeBase()
    return _KNOWLEDGE_BASE
