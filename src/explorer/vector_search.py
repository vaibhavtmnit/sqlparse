"""
vector_search.py - Optional Vector Search Fallback

Allows the explorer to execute semantic similarity searches against the AST descriptions
using either FAISS or LanceDB.
"""
from typing import List, Dict, Any

from loguru import logger
from langchain_core.documents import Document

class ExplorerVectorStore:
    """Base generic store interface"""
    def add_texts(self, texts: List[str], metadatas: List[Dict[str, Any]]):
        pass
        
    def similarity_search(self, query: str, k: int = 3) -> List[Document]:
        return []

class FaissVectorStore(ExplorerVectorStore):
    """FAISS Implementation for purely in-memory rapid fallback."""
    def __init__(self, embeddings_model):
        self.embeddings_model = embeddings_model
        self.vectorstore = None
        
    def add_texts(self, texts: List[str], metadatas: List[Dict[str, Any]]):
        try:
            from langchain_community.vectorstores import FAISS
            self.vectorstore = FAISS.from_texts(texts, self.embeddings_model, metadatas=metadatas)
            logger.debug(f"FAISS vector store initialized with {len(texts)} documents.")
        except ImportError as e:
            logger.error(f"Failed to load FAISS: {e}")
            
    def similarity_search(self, query: str, k: int = 3) -> List[Document]:
        if not self.vectorstore:
            return []
        return self.vectorstore.similarity_search(query, k=k)

class LanceDBVectorStore(ExplorerVectorStore):
    """LanceDB Implementation for persistent hybrid fallback."""
    def __init__(self, embeddings_model, uri: str = "./lancedb_explorer"):
        self.embeddings_model = embeddings_model
        self.uri = uri
        self.vectorstore = None
        
    def add_texts(self, texts: List[str], metadatas: List[Dict[str, Any]]):
        try:
            from langchain_community.vectorstores import LanceDB
            import lancedb
            
            db = lancedb.connect(self.uri)
            table_name = "explorer_docs"
            
            # Convert texts to docs
            docs = [Document(page_content=t, metadata=m) for t, m in zip(texts, metadatas)]
            self.vectorstore = LanceDB.from_documents(docs, self.embeddings_model, connection=db, table_name=table_name)
            logger.debug(f"LanceDB vector store initialized at {self.uri} with {len(texts)} documents.")
        except ImportError as e:
            logger.error(f"Failed to load LanceDB: {e}")
            
    def similarity_search(self, query: str, k: int = 3) -> List[Document]:
        if not self.vectorstore:
            return []
        return self.vectorstore.similarity_search(query, k=k)

def initialize_vector_search(enricher: Any, embeddings_model: Any, backend: str = "faiss") -> ExplorerVectorStore:
    """Read the enricher's AST data and push into the requested vector database."""
    texts = []
    metadatas = []
    
    if hasattr(enricher, "entities_df") and not enricher.entities_df.empty:
        records = enricher.entities_df.to_dict('records')
        for rec in records:
            # Flatten description list if it exists
            desc = rec.get("description", [])
            if isinstance(desc, list):
                desc = "\n".join([str(d) for d in desc])
                
            code_refs = rec.get("chunk_ids", [])
            
            text = f"Entity: {rec.get('entity_name')}\nType: {rec.get('entity_type')}\nDescription:\n{desc}"
            texts.append(text)
            metadatas.append({
                "entity_name": rec.get("entity_name"),
                "entity_type": rec.get("entity_type")
            })
            
    store = LanceDBVectorStore(embeddings_model) if backend == "lancedb" else FaissVectorStore(embeddings_model)
    if texts:
        store.add_texts(texts, metadatas)
        
    return store
