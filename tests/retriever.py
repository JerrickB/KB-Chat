import chromadb
from chromadb.config import Settings
from langchain_chroma import Chroma
from os import getcwd, environ, listdir
from pathlib import Path
from langchain.retrievers import ParentDocumentRetriever
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.storage import InMemoryStore
from langchain_community.document_loaders import TextLoader
from sys import path
path.append(r'C:\Users\Izogie\Desktop\Folders\Projects\Python\KB Chat\src')
from modules.SourceManager import SourceManager


PROJ_DIR = Path(getcwd()).parent
DB_DIR = PROJ_DIR / "chroma"

from langchain_huggingface import HuggingFaceEmbeddings
embedding_function = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

query = "what does steel do"

docs = []
for filename in listdir(str(PROJ_DIR / "data")):
    loader = TextLoader(str(PROJ_DIR / f"data/{filename}"))
    docs.extend(loader.load())

vectorstore = Chroma.from_documents(
    docs, 
    embedding_function,
    collection_name="full_documents", 
    persist_directory=str(DB_DIR))
print("There are", vectorstore._collection.count(), "in the collection")

child_splitter = RecursiveCharacterTextSplitter(chunk_size=400)
parent_splitter = RecursiveCharacterTextSplitter(chunk_size=2000)
store = InMemoryStore()
retriever = ParentDocumentRetriever(
    vectorstore=vectorstore, 
    docstore=store,
    parent_splitter=parent_splitter,
    child_splitter=child_splitter)
retrieved_docs = retriever.invoke("steel")
print(len(list(store.yield_keys())))
print(retrieved_docs)