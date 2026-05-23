"""Knowledge Base page — RAG inspector."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from core import CLAUSE_NAMES, BASE_DIR, load_config, get_embedding_model, get_active_clauses
from components import page_head
from icons import icon


def render() -> None:
    page_head(
        "Knowledge Base",
        "Advanced — Inspect the ISO 27001 reference material the AI used when writing each document.",
    )

    st.info(
        "**What is this?** When the AI generates your documents, it searches a built-in library of "
        "ISO 27001 audit requirements to understand what each document must contain. "
        "This tab lets you see exactly which reference entries were looked up for any document — "
        "useful if you want to verify the AI's sources or understand why a section was written a certain way."
    )

    cfg = load_config()

    try:
        import chromadb
    except ImportError:
        st.error("Required package missing. Run `pip install chromadb` in your terminal.")
        return

    chroma_path = BASE_DIR / cfg["rag"]["chroma_db_path"]
    if not chroma_path.exists():
        st.warning("ISO knowledge base not built yet. Run `python rag_setup.py` from the installation folder.")
        return

    _active = get_active_clauses()
    cid = st.selectbox(
        "Select a document to inspect",
        list(_active.keys()),
        format_func=lambda x: f"{x} — {_active[x]}",
    )

    if st.button("Show ISO reference entries", type="primary"):
        with st.spinner("Looking up reference entries…"):
            try:
                embed_model = get_embedding_model()
                client      = chromadb.PersistentClient(path=str(chroma_path))
                collection  = client.get_collection(cfg["rag"]["collection_name"])
                query       = f"ISO 27001 clause {cid} requirements audit criteria"
                embedding   = embed_model.encode([query]).tolist()

                exact_docs, exact_metas = [], []
                try:
                    exact       = collection.get(where={"control_id": {"$eq": cid}})
                    exact_docs  = exact.get("documents", [])
                    exact_metas = exact.get("metadatas", [])
                except Exception:
                    pass

                sem      = collection.query(query_embeddings=embedding, n_results=5)
                sem_docs  = sem["documents"][0]
                sem_metas = sem["metadatas"][0]

            except Exception as e:
                st.error(f"Could not query knowledge base: {e}")
                return

        if exact_docs:
            st.markdown('<div class="card-head" style="margin-bottom:8px"><h3 class="card-title">Direct match</h3></div>', unsafe_allow_html=True)
            for doc, meta in zip(exact_docs, exact_metas):
                with st.expander(f"[{meta['control_id']}] {meta['control_name']}  ·  source: {meta['sheet']}"):
                    st.text(doc[:800])

        st.markdown('<div class="card-head" style="margin:16px 0 8px"><h3 class="card-title">Related entries (top 5 by similarity)</h3></div>', unsafe_allow_html=True)
        for doc, meta in zip(sem_docs, sem_metas):
            label = " — direct match" if meta["control_id"] == cid else ""
            with st.expander(f"[{meta['control_id']}] {meta['control_name']}{label}"):
                st.text(doc[:800])
