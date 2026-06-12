import os
import sys
import json
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple

# Ensure project root is in python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.vector_store import get_vector_store
from app.database import init_db


# =============================================================================
# 1. PARSING INTERFACE (SRP: Decoupled Parsing and Chunking)
# =============================================================================
class DocumentParser(ABC):
    """Abstract interface defining the contract for parsing policy document formats."""
    
    @abstractmethod
    def parse_file_to_chunks(self, file_path: str, category: str) -> Tuple[List[str], List[Dict]]:
        """Parses a policy document, breaks it down into chunks, and returns (chunks, metadatas)."""
        pass


# =============================================================================
# 2. CONCRETE PARSERS (Open/Closed Principle)
# =============================================================================
class XmlPolicyParser(DocumentParser):
    """Parses XML-formatted policy manuals, executing tag-aware chunk split operations."""
    
    def parse_file_to_chunks(self, file_path: str, category: str) -> Tuple[List[str], List[Dict]]:
        chunks: List[str] = []
        metadatas: List[Dict] = []
        
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            dept = root.attrib.get("department", "Corporate")
            comp = root.attrib.get("company", "Corporate")
            
            for policy in root.findall(".//policy"):
                policy_id = policy.attrib.get("id", "UNKNOWN")
                policy_title = policy.attrib.get("title", "Untitled Policy")
                min_permission = int(policy.attrib.get("min_permission", "2"))
                summary = policy.find("summary")
                summary_text = summary.text.strip() if summary is not None else ""
                
                for idx, section in enumerate(policy.findall("section")):
                    sec_title = section.attrib.get("title", f"Section {idx+1}")
                    sec_content = section.text.strip() if section.text else ""
                    if not sec_content:
                        continue
                        
                    # Construct structural context block
                    chunk_text = (
                        f"Company: {comp}\n"
                        f"Department: {dept}\n"
                        f"Policy: {policy_title} (ID: {policy_id})\n"
                        f"Section: {sec_title}\n"
                        f"Summary: {summary_text}\n"
                        f"Content: {sec_content}"
                    )
                    
                    meta = {
                        "policy_id": policy_id,
                        "policy_title": policy_title,
                        "section_title": sec_title,
                        "min_permission_level": min_permission,
                        "category": category,
                        "source": os.path.basename(file_path)
                    }
                    
                    chunks.append(chunk_text)
                    metadatas.append(meta)
                    
        except Exception as e:
            print(f"[ERROR] XmlPolicyParser failed on {file_path}: {e}", file=sys.stderr)
            
        return chunks, metadatas


class JsonPolicyParser(DocumentParser):
    """Parses JSON IT guidelines, transforming structured fields into RAG chunks."""
    
    def parse_file_to_chunks(self, file_path: str, category: str) -> Tuple[List[str], List[Dict]]:
        chunks: List[str] = []
        metadatas: List[Dict] = []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            comp = "Corporate"
            dept = "IT Security"
            
            for policy in data.get("policies", []):
                policy_id = policy.get("id", "UNKNOWN")
                policy_title = policy.get("title", "Untitled Policy")
                min_permission = int(policy.get("min_permission", 2))
                summary_text = policy.get("summary", "")
                
                for sec in policy.get("sections", []):
                    sec_title = sec.get("name", "Section")
                    sec_content = sec.get("content", "")
                    if not sec_content:
                        continue
                        
                    # Construct structural context block
                    chunk_text = (
                        f"Company: {comp}\n"
                        f"Department: {dept}\n"
                        f"Policy: {policy_title} (ID: {policy_id})\n"
                        f"Section: {sec_title}\n"
                        f"Summary: {summary_text}\n"
                        f"Content: {sec_content}"
                    )
                    
                    meta = {
                        "policy_id": policy_id,
                        "policy_title": policy_title,
                        "section_title": sec_title,
                        "min_permission_level": min_permission,
                        "category": category,
                        "source": os.path.basename(file_path)
                    }
                    
                    chunks.append(chunk_text)
                    metadatas.append(meta)
                    
        except Exception as e:
            print(f"[ERROR] JsonPolicyParser failed on {file_path}: {e}", file=sys.stderr)
            
        return chunks, metadatas


# =============================================================================
# 3. VECTOR STORAGE INDEXING SERVICE
# =============================================================================
class VectorDatabaseIndexer:
    """Invokes embeddings encoders, maps context keys, and stores texts into the database."""
    
    def __init__(self, vector_store=None):
        self.vector_store = vector_store or get_vector_store()

    def index_texts(self, texts: List[str], metadatas: List[Dict], ids: List[str]):
        """Generates embeddings and inserts/indexes documents into the vector database."""
        if not texts:
            print("[WARNING] VectorDatabaseIndexer: Received empty texts list.")
            return
            
        # Clear existing indices for local Chroma to prevent document duplication
        if settings.VECTOR_STORE == "chroma":
            try:
                self.vector_store.delete(ids=ids)
            except Exception:
                pass
                
        self.vector_store.add_texts(texts=texts, metadatas=metadatas, ids=ids)


# =============================================================================
# 4. COORDINATION PIPELINE
# =============================================================================
class DocumentIngestionPipeline:
    """Coordinates parsing strategies and indexing services to execute ingestion."""
    
    def __init__(self, parsers: Dict[str, DocumentParser], indexer: VectorDatabaseIndexer):
        self.parsers = parsers
        self.indexer = indexer
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

    def run_ingestion(self):
        print("[INFO] DocumentIngestionPipeline: Running database and table initialization...")
        init_db()
        
        all_chunks: List[str] = []
        all_metadatas: List[Dict] = []
        all_ids: List[str] = []
        
        # Files schedules
        ingestion_tasks = [
            ("hr_policy.xml", "xml", "HR"),
            ("it_security_policy.json", "json", "IT"),
            ("developer_handbook.xml", "xml", "Dev")
        ]
        
        for filename, parser_key, category in ingestion_tasks:
            file_path = os.path.join(self.data_dir, filename)
            if not os.path.exists(file_path):
                print(f"[ERROR] DocumentIngestionPipeline: Policy file not found: {file_path}")
                continue
                
            parser = self.parsers.get(parser_key)
            if not parser:
                print(f"[ERROR] DocumentIngestionPipeline: No parser registered for key: {parser_key}")
                continue
                
            print(f"[INFO] Parsing '{category}' documents from {filename}...")
            chunks, metadatas = parser.parse_file_to_chunks(file_path, category)
            all_chunks.extend(chunks)
            all_metadatas.extend(metadatas)

        # Generate unique database IDs
        for i, meta in enumerate(all_metadatas):
            doc_id = f"{meta['category']}_{meta['policy_id']}_sec_{i}"
            all_ids.append(doc_id)

        if not all_chunks:
            print("[ERROR] DocumentIngestionPipeline: No document chunks loaded. Aborting.")
            return

        # Execute indexing
        print(f"[INFO] Indexing {len(all_chunks)} chunks to vector store: {settings.VECTOR_STORE}...")
        self.indexer.index_texts(texts=all_chunks, metadatas=all_metadatas, ids=all_ids)
        print("[SUCCESS] DocumentIngestionPipeline: Policy database index successfully seeded!")


# =============================================================================
# 5. ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    # Register document formats
    active_parsers = {
        "xml": XmlPolicyParser(),
        "json": JsonPolicyParser()
    }
    
    # Instantiate database indexer service
    database_indexer = VectorDatabaseIndexer()
    
    # Coordinate pipeline run
    pipeline = DocumentIngestionPipeline(
        parsers=active_parsers,
        indexer=database_indexer
    )
    pipeline.run_ingestion()
