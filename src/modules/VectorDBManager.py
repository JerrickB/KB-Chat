# Initialize and handle Chroma DB and wrap it in langchain
import uuid
from random import randint
from os import environ
from pathlib import Path

import chromadb
from chromadb.config import Settings
import chromadb.utils.embedding_functions as embedding_fns

from langchain.embeddings import HuggingFaceEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain.chains.query_constructor.base import AttributeInfo

from ratelimit import limits, RateLimitException, sleep_and_retry
from backoff import on_exception, expo
import google.api_core.exceptions as google_exceptions

from modules.utils import load_config
load_config()
from google.generativeai import GenerativeModel, configure
configure(api_key=environ["GOOGLE_API_KEY"])

DB_DIR = Path(__file__).parent.parent / "chroma"

class VectorDBManager:
    """
    Manages the VectorDB and wraps it with Langchain.
    """
    def __init__(self, db_dir: Path = DB_DIR) -> None:
        """
        Constructor for VectorDBManager class.

        Args:
            db_dir (Path): Path to the database directory.

        Returns:
            None
        """
        self.db_dir = db_dir
        
        self.chroma_client = chromadb.PersistentClient(
            path=str(db_dir),
            settings=Settings(allow_reset=True)
        )
        self.chroma_embedding_function = embedding_fns.OpenAIEmbeddingFunction(api_key=environ["OPENAI_API_KEY"])
        self.collection = self.chroma_client.get_or_create_collection("coppermind", embedding_function=self.chroma_embedding_function)

        self.model = GenerativeModel(model_name="gemini-1.5-flash")

    def fresh_db(self) -> None:
        """
        Resets the database.

        Args:
            None

        Returns:
            None
        """
        self.chroma_client.reset()
        self.collection = self.chroma_client.get_or_create_collection("coppermind", embedding_function=self.chroma_embedding_function)

    def _init_langchaindb(self) -> None:
        """
        Initializes the LangchainDB.

        Args:
            None

        Returns:
            None
        """
        self.langdb = Chroma(
            collection_name="coppermind",
            embedding_function=OpenAIEmbeddings(),
            client=self.chroma_client,
        )

    def _init_metadata_field_info(self) -> None:
        """
        Initializes the metadata field info.

        Args:
            None

        Returns:
            None
        """
        self.metadata_field_info = [
            AttributeInfo(
                name="article_title",
                description="title of parent article",
                type="string",
            ),
            AttributeInfo(
                name="paragraph_header",
                description="header in article_title under which content was located",
                type="string",
            ),
            AttributeInfo(
                name="paragraph_order",
                description="order of paragraph under the paragraph_header",
                type="integer",
            ),
            AttributeInfo(
                name="links",
                description="list of article_titles that are directly related to the parent article",
                type="string",
            ),
        ]
        self.doc_content_description = "paragraph of an article from the coppermind, a knowledgebase for everything in the literary universe of the Cosmere, written by Brandon Sanderson"

    MINUTE = 60
    # rate is 1 QPS.
    @sleep_and_retry  # If there are more requests to this function than rate, sleep shortly
    @on_exception(
        expo, google_exceptions.ResourceExhausted, max_tries=10  # if we receive exceptions from Google API, retry
    )
    @limits(calls=40, period=MINUTE)
    def call_prompt_in_rate(self, prompt: str) -> str:
        """
        Calls the LLM model and applies rate limits.

        Args:
            prompt (str): The prompt.

        Returns:
            str: The generated content.
        """
        # return model.invoke(prompt) #Langchain openai
        return self.model.generate_content(prompt)


    def ingest_articles(self, data, with_keywords=False):
        """Ingests structured article data into ChromaDB."""
        namespace_uuid = uuid.UUID('f81d4fae-7dec-11d0-a765-00a0c91e6bf6')
        documents = []
        metadatas = []
        ids = []

        for article in data:
            if article["sections"] is None:
                continue
                # OpenAI and Google Embeddings do not like empty strings
                # TODO: Implement embeddings for redirect pages

                # documents.append("")
                # metadatas.append({
                #     "article_title": article["title"],
                #     "paragraph_header": article["title"],
                #     "paragraph_order": 0,
                #     "links": ', '.join(article["links"]),
                # })
                # ids.append(str(uuid.uuid5(namespace_uuid, article['title'])))
            else:
                for paragraph in article["sections"]:
                    keywords = ""
                    if with_keywords:
                        content = paragraph['content']
                        prompt = f"""
                            For the following paragraph, extract a list of keywords that will be used as metadata when the paragraph is stored in a vector database. The keywords will be used to help return accurate results when the database is queried. the list must look like this "keyword1, keyword 2, keyword 3, ..."

                            Here is the paragraph:
                            ```
                            {content}
                            ```
                            """
                        # response = model.generate(prompt)
                        response = self.call_prompt_in_rate(prompt)
                        try:
                            keywords = response.text
                            # keywords = response.content
                        except Exception as e:
                            print(e)
                            print(f"{i}, {j}", content)
                            keywords=""
                            continue
                    documents.append(paragraph["content"])
                    metadatas.append({
                        "article_title": article["title"],
                        "paragraph_header": paragraph['title'],
                        "paragraph_order": paragraph["order"],
                        "links": ', '.join(article["links"]),
                        "keywords": keywords,
                    })
                    ids.append(str(uuid.uuid5(namespace_uuid, f"{paragraph['title']}_{paragraph['order']}_{randint(0,10000)}")))  # Create unique IDs

        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids 
        )
