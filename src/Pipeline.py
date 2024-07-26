# Proof of concept pipleine

# Import modules
from modules.SourceManager import SourceManager
from modules.VectorDBManager import VectorDBManager
from modules.CustomParentDocumentRetriever import CustomParentDocRetriever

from langchain_experimental.text_splitter import SemanticChunker
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.storage import InMemoryStore
store = InMemoryStore()

from langchain.retrievers.self_query.base import SelfQueryRetriever
from langchain.retrievers.self_query.chroma import ChromaTranslator

from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import FlashrankRerank

from langchain_google_genai import GoogleGenerativeAI

class RAGPipeline:
    def __init__(self) -> None:
        self.source_manager = SourceManager()
        # Init vector_manager
        self.vector_manager = VectorDBManager()
        self.llm = GoogleGenerativeAI(model="gemini-1.5-flash")

        self.init_retriever()
        self.init_compressor()

    # Check for new pages

    # If new pages, process pages
    def load_processed_pages(self):
        """
        Load processed pages from the source manager and ingest them into the vector manager.
        """
        # Load processed pages
        # This method loads the processed pages from the source manager
        # and ingests them into the vector manager.
        # The processed pages are loaded from the file "processed_articles.jsonl"
        # using the `load_json` method of the `source_manager` object.
        # The loaded data is then passed to the `ingest_articles` method of the `vector_manager` object.
        data = self.source_manager.load_json("processed_articles.jsonl")
        self.vector_manager.ingest_articles(data)

    # Init retriever
    def init_retriever(self) -> None:
        """
        Initializes the retriever.

        Initializes the retriever by calling the private methods
        `_init_langchaindb` and `_init_metadata_field_info` of the
        `vector_manager` object. Then creates a `SelfQueryRetriever` object
        with the `llm` object and the necessary parameters.

        Returns:
            None
        """
        # Initialize LangchainDB
        self.vector_manager._init_langchaindb()
        # Initialize metadata field info
        # self.vector_manager._init_metadata_field_info()
        # Create SelfQueryRetriever object
        # self.retriever = SelfQueryRetriever.from_llm(
        #     self.llm,  # GoogleGenerativeAI object
        #     vectorstore=self.vector_manager.langdb,  # LangchainDB object
        #     document_contents=self.vector_manager.doc_content_description,  # Document contents
        #     metadata_field_info=self.vector_manager.metadata_field_info,  # Metadata field info
        #     structured_query_translator=ChromaTranslator()  # ChromaTranslator object
        # )
        self.splitter = SemanticChunker(HuggingFaceEmbeddings())
        self.docstore = InMemoryStore()
        self.retriever = CustomParentDocRetriever(
            vectorstore=self.vector_manager.langdb,
            docstore=self.docstore,
            child_splitter=self.splitter
        )

    # Init compressor
    def init_compressor(self) -> None:
        """
        Initializes the compressor and rerank retriever.

        Returns:
            None
        """
        self.compressor: FlashrankRerank = FlashrankRerank()
        self.rerank_retriever: ContextualCompressionRetriever = ContextualCompressionRetriever(
            base_compressor=self.compressor, 
            base_retriever=self.retriever
        )

    # Perform Rag
    def perform_rag(self, query: str, verbose: bool = False) -> str:
        """
        Performs a Retrieval-and-Generation (RAG) query on the provided query string.

        Args:
            query (str): The query string to perform the RAG on.
            verbose (bool, optional): Whether to print the retrieved documents and
                the generated response. Defaults to False.

        Returns:
            str: The generated response from the language model.
        """
        if not self.compressor:
            self._init_retriever()
            self._init_compressor()

        # Retrieve documents using the rerank retriever
        llm_docs = self.rerank_retriever.invoke(query)

        # Print the retrieved documents if verbose is True
        if verbose:
            print(llm_docs)

        # Prepare the prompt for the language model
        prompt = (
            f"""
            Use the below context to assist in answering this question: {query}

            context
            {llm_docs}
            """
        )

        # Invoke the language model with the prompt
        llm_response = self.llm.invoke(prompt)

        # Print the generated response if verbose is True
        if verbose:
            print(llm_response)
        
        # Format response
        llm_response = llm_response.strip()
        formatted = f"""
{llm_response}

Sources:"""
        
        print(formatted)
        for i, source in enumerate(llm_docs,1):
            print(f"{i} - {source.page_content}")

        # Return the generated response
        return llm_response, llm_docs
