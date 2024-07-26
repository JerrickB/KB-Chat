from mwclient import Site
import mwparserfromhell as mwp
import json
from re import match
from typing import List, Dict, Any, Tuple, Union
from langchain_core.documents import Document

import logging
import logging.config 
logging.basicConfig(
    level=logging.DEBUG,  # Set the minimum log level to capture
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  
    filename="../data/KB_chat.log"
)

class SourceManager:
	def __init__(self, wiki_endpoint: str = "coppermind.net", text_splitter = None) -> None:
			"""
			Constructor for SourceManager class.

			Args:
				wiki_endpoint (str, optional): The wiki endpoint URL. Defaults to "coppermind.net".
				text_splitter (optional): The text splitter to use for splitting the text into smaller chunks.

			Returns:
				None
			"""
			# Set the wiki endpoint URL
			self.wiki_endpoint = wiki_endpoint
			
			# Set the user agent for the requests
			self.user_agent: str = "TheataTest (numberticket+cm@proton.me)"
			
			# Initialize an empty list to store the pages
			self.pages: List[str] = []
			
			# Initialize an empty list to store the data
			self.data: List[Dict[str, Any]] = []
			
			# Initialize the site object as None
			self.site = None
			
			# Set the text splitter
			self.text_splitter = text_splitter
			
			# Get the logger for the current module
			self.logger = logging.getLogger(__name__) 
	
	def _init_mwclient(self, retries: int = 3) -> None:
		"""
		Initializes MWClient with the given retries.

		Args:
			retries (int): The number of times to retry connecting to the wiki endpoint. Defaults to 3.
			retries (int, optional): The number of times to retry connecting to the wiki endpoint. Defaults to 3.

		Returns:
			None
		"""
		for i in range(retries):
			try:
				self.site = Site(self.wiki_endpoint, clients_useragent=self.user_agent)
				self.logger.info(f"MWClient Connected with {self.wiki_endpoint}")
				print(f"MWClient Connected with {self.wiki_endpoint}")
				return	
			except Exception as e:
				self.logger.error(f"MWClient unable to connect with {self.wiki_endpoint} - {e}")
			except Exception:
				pass
		print(f"MWClient unable to connect with {self.wiki_endpoint}")
		

	def load_json(self, filename: str = "pages.jsonl") -> list[dict]:
		"""Loads data from a JSONLines file, or creates an empty one if it doesn't exist.

		Args:
			filename (str): The name of the JSONLines file. Defaults to "pages.jsonl".

		Returns:
			list[dict]: A list of dictionaries loaded from the file, or an empty list if the file didn't exist.
		"""
		data: list[dict] = []
		try:
			with open(filename, 'r') as file:
				for line in file:
					data.append(json.loads(line))
		except FileNotFoundError:
			# File doesn't exist, create an empty one
			with open(filename, 'w') as file:
				pass  # Do nothing, just create the file

		return data

	def save_json(self, data: Union[list, set], filename: str = "articles.jsonl") -> None:
		"""
		Save data to a JSON file.

		Args:
			data (Union[list, set]): The data to save. If it is a set, it will be converted to a list.
			filename (str, optional): The name of the file to save the data to. Defaults to "articles.jsonl".

		Returns:
			None
		"""
		try:
			with open(filename, 'w') as file:
				if isinstance(data, set):
					data = list(data)
				for entry in data:
					file.write(json.dumps(entry) +'\n')
				self.logger.info(f"{filename} saved")
				print(f"{filename} saved")
		except Exception as e:
			self.logger.error(f"Failed to save {filename} - {e}")
			print(f"Failed to save {filename} - {e}")

	def wiki_parse(self, title: str) -> Tuple:
		"""
		Parse a wiki page and return a tuple containing the page name and a MWParser Page object.

		Args:
			title (str): The title of the page to parse.

		Returns:
			Tuple[str, mwp.Page]: A tuple containing the page name and the parsed MWParser Page object.
		"""
		if self.site is None:
			self._init_mwclient()
		page = self.site.pages[title]
		self.logger.info(f"Parsing {title}")
		return page.name, page


	def wiki_parse_pages(
		self, page_titles: List[str], load: bool = False, update: bool = False
	) -> List[Dict[str, List]]:
		"""
		Parse multiple pages, append them to the existing list, and append them to JSON with raw wikicode objects.

		Args:
		    page_titles (List[str]): The titles of the pages to parse.
		    load (bool, optional): Whether to load the existing list of pages from JSON. Defaults to False.
		    update (bool, optional): Whether to update the existing list of pages. Defaults to False.

		Returns:
		    List[Dict[str, List[Union[mwp.Page, str]]]]: A list of dictionaries containing the page name and the parsed MWParser Page object.
		"""
		# Load existing list of pages if needed
		if load and self.pages:
			self.pages = self.load_json()

		# If not updating, filter out already-parsed pages
		# if not update:
		# 	page_titles = [title for title in page_titles if title not in [page['title'] for page in self.pages]]

		# Parse and append new pages
		self.pages.extend(
			{'title': title, 'page': self.site.pages[title]}
			for title in page_titles
		)

		return self.pages


	# convert sections into documents w/ metadata
	def get_sections(self, page, keywords: bool=False):
		"""
		Parse the sections of a page and return them as a list of dictionaries with content and metadata.

		Args:
		    page (mwp.Page): The page to parse.
		    keywords (bool, optional): Whether to extract keywords from the sections. Defaults to False.

		Returns:
		    List[Dict[str, Union[str, Dict]]]: A list of dictionaries with content and metadata for each section.
		"""
		sections = []
		article_title = page.page_title
		self.logger.info(f"Procssing {article_title}")
		print(f"Procssing {article_title}")
		headings = [article_title] + [str(heading.title).strip() for heading in mwp.parse(page.text()).filter_headings()]
		parsed = mwp.parse(page.text())

		if page.redirects_to() is not None:
			doc = {}
			parent_article = page.redirects_to().page_title
			doc['content'] = parent_article
			doc['metadata'] = {
				'heading': f"Redirects to {parent_article}",
				'order': 1,
				'parent_article': parent_article,
				'keywords': parent_article 
			}
			sections.append(doc)
		else:
			for i in range(len(parsed.get_sections()) - 1): # skip the last section "Notes", it's not useful
				content = mwp.parse(page.text(section=i)).strip_code()
				keywords = ''
				if keywords:
					prompt = f"""
						For the following paragraph, extract a list of keywords that will be used as metadata when the paragraph is stored in a vector database. The keywords will be used to help return accurate results when the database is queried. the list must look like this "keyword1, keyword 2, keyword 3, ..."

						Here is the paragraph:
						```
						{content}
						```
						"""
					# response = model.generate(prompt)
					response = call_prompt_in_rate(prompt)
					try:
						keywords = response.text
					except Exception as e:
						print(e)
						print(f"{i}, {j}", content)
						keywords=""
						continue
				if self.text_splitter is not None:
					chunks = self.text_splitter.split_text(content)
					for chunk in chunks:
						doc = {}
						doc['content'] =  article_title + ' - ' + chunk
						doc['metadata'] = {
							'heading': headings[i],
							'order': i, 
							'parent_article': article_title,
							'keywords': keywords
							}
						sections.append(doc)
				else:
					doc = {}
					doc['content'] = article_title + ' - ' + content
					doc['metadata'] = {
						'heading': headings[i],
						'order': i, 
						'parent_article': article_title,
						'keywords': keywords
						}
					sections.append(doc)
		return sections

	def prep_data_vector(self, page_titles, save=False):
		self._init_mwclient()
		pages = self.wiki_parse_pages(page_titles)
		for page in pages:
			self.data.extend(self.get_sections(page['page']))
		if save: self.save_json(self.data, 'sectioned_articles.jsonl')
		return self.data
    
	def to_documents(self, data=None):
		data = data or self.data
		return [Document(page_content=doc['content'], metadata=doc['metadata']) for doc in data]
	
	# I don't think I need any of these links anymore, to be honest. They were for the Graph DB. Will refactor them when I find a more suitble graph db
	
	# def clean_wiki_tags(self, page) -> List[str]:
	# 	"""
	# 	Cleans and formats a list of wiki tags into strings for linking in a graph database.
	
	# 	Args:
	# 		page: A MediaWiki page.
	
	# 	Returns:
	# 		A list of cleaned and formatted tag strings.
	# 	"""
	# 	tags = page.filter_templates()
	# 	cleaned_tags: Set[str] = set()
	
	# 	for tag in tags:
	# 		cleaned_tag = tag.replace('{', '').replace('}', '')
	
	# 		# Handle specific tag formats
	# 		if cleaned_tag.startswith(("update", "character", "cite", "quote", "sidequote", "image", "partial", "for", "file")):
	# 			continue
	# 		elif tag.startswith("{{wob ref|"):
	# 			cleaned_tag = f"ref-wob-{cleaned_tag.split('|')[1]}"
	# 		elif tag.startswith("{{book ref|"):
	# 			parts = cleaned_tag.split('|')
	# 			cleaned_tag = "ref-book-" + "-".join(parts[1:])
	# 		elif tag.startswith("{{epigraph ref|"):
	# 			parts = cleaned_tag.split('|')
	# 			cleaned_tag = "ref-epi-" + "-".join(parts[1:])
	# 		elif tag.startswith("{{tag"):
	# 			# Split on pipe (|) and ignore the 'tag' part
	# 			parts = cleaned_tag.split('|')[1:]

	# 			# Handle "cat tag" or "tag|cat=" cases
	# 			if parts[0] == "cat":
	# 				cleaned_tag = parts[2].split('=')[0]  # Get the category name
	# 			elif parts[0] == "army":
	# 				cleaned_tag = parts[1]
	# 			elif "=" in parts[-1]:
	# 				cleaned_tag = parts[0]  # Get the main tag
	# 			else:
	# 				cleaned_tag = '_'.join(parts)
	# 		else:  # Handle other formats
	# 			# Split on pipe (|) and take only the first part
	# 			parts = cleaned_tag.split('|')
	# 			cleaned_tag = parts[0].replace('#', '_').replace(' ', '_').lower()

	# 		if cleaned_tag in {"cat_tag", "cite"}:
	# 			continue

	# 		if cleaned_tag:
	# 			cleaned_tags.add(cleaned_tag.replace("'s", ""))

	# 	return list(cleaned_tags)

	# def clean_wiki_links(self, page):
	# 	"""Removes aliases and duplicates from a list of MediaWiki links.

	# 	Args:
	# 		links: A list of strings representing MediaWiki links (e.g., '[[Link]]', '[[Link|Alias]]').

	# 	Returns:
	# 		A new list with unique links, aliases removed.
	# 	"""
	# 	links = page.filter_wikilinks()
	# 	cleaned_links = []
	# 	seen_links = set()  # Track unique links

	# 	for link in links:
	# 		matches = match(r'\[\[(.*?)(?:\|.*?)?\]\]', str(link)) 
	# 		if matches:
	# 			link_text = matches.group(1)  # Extract link text (without alias)
	# 			if link_text not in seen_links:
	# 				cleaned_links.append(link_text)
	# 				seen_links.add(link_text)

	# 	return cleaned_links

	# def get_links(self, page):
	# 	out_links = set()
	# 	out_links.update(self.clean_wiki_links(page))
	# 	out_links.update(self.clean_wiki_tags(page))
	# 	result = set()
	# 	for name in out_links:
	# 		# Check if the name is a substring of any other name in the set
	# 		is_redundant = any(name in other_name and name != other_name for other_name in out_links)
	# 		if not is_redundant:
	# 			result.add(name)

	# 	return list(result)

	# def prep_data_graph(self, page_titles):
	# 	self._init_mwclient()
	# 	pages = self.wiki_parse_pages(page_titles)
	# 	for page in pages:
	# 		prepped_page = self.process_page(page)
	# 		self.data.append(prepped_page)
	# 	self.save_json(self.data)
	# 	return self.data