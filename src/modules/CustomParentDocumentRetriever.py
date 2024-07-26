from langchain_core.documents import Document
from langchain.retrievers import MultiVectorRetriever
from langchain_text_splitters import TextSplitter
from typing import Union, Optional, Sequence, Any
import uuid

class CustomParentDocRetriever(MultiVectorRetriever):
    child_splitter: Any
    """The text splitter to use to create child documents."""

    """The key to use to track the parent id. This will be stored in the
    metadata of child documents."""
    parent_splitter: Optional[TextSplitter] = None
    """The text splitter to use to create parent documents.
    If none, then the parent documents will be the raw documents passed in."""

    child_metadata_fields: Optional[Sequence[str]] = None
    """Metadata fields to leave in child documents. If None, leave all parent document 
        metadata.
    """
    def _to_document(self, data) -> Document:
        return Document(page_content=data['content'], metadata=data['metadata'])
    
    def save_txt(self, data: Union[list, set], filename: str) -> None:
        with open(filename + '.txt', 'w') as file:
            file.write(str(data))
    
    def load_txt(self, filename: str) -> list[dict]:
        with open(filename + '.txt', 'r') as file:
            return eval(file.read())
    
    def load_processed(
            self,
            load_prefix = 'semantic'):
        docs = self.load_txt(f'{load_prefix}_docs')
        full_docs = self.load_txt(f'{load_prefix}_full_docs')
        self.vectorstore.add_documents(docs)
        self.docstore.mset(full_docs)
        

    def _split_docs_for_adding(
            self,
            documents,
            save=True,
            save_prefix = 'semantic'
        ):
        # feed semantic splitter to custom ParentDocumentRetriever
        if not isinstance(documents[0], Document):
            documents = [self._to_document(doc) for doc in documents]
        full_docs = []
        docs = []
        for i, doc in enumerate(documents):
            id = str(uuid.uuid4())
            full_docs.append((id, doc))
            
            chunks = self.child_splitter.split_documents([doc])
            for child in chunks:
                if not child.page_content.startswith(f"{child.metadata['parent_article']} - "):
                    child.page_content = f"{child.metadata['parent_article']} - {child.page_content}"
                child.metadata['doc_id'] = id
                docs.append(child)
        if save:
            self.save_txt(full_docs, f'{save_prefix}_full_docs')
            self.save_txt(docs, f'{save_prefix}_docs')
        return docs, full_docs

    def add_documents(self, documents):
        docs, full_docs = self._split_docs_for_adding(documents)
        self.vectorstore.add_documents(docs)
        self.docstore.mset(full_docs)