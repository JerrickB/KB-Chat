from mwclient import Site
import mwparserfromhell as mwp
import json
from re import match
from typing import List, Dict, Any, Tuple, Union

class SourceManager:
	def __init__(self, wiki_endpoint: str = "coppermind.net") -> None:
			"""
			Constructor for SourceManager class.

			Args:
				wiki_endpoint (str, optional): The wiki endpoint URL. Defaults to "coppermind.net".

			Returns:
				None
			"""
			self.wiki_endpoint = wiki_endpoint
			self.user_agent: str = "TheataTest (numberticket+cm@proton.me)"
			self.pages: List[str] = []
			self.data: List[Dict[str, Any]] = []

	def _init_mwclient(self, retries: int = 3) -> None:
		"""
		Initializes MWClient with the given retries.

		Args:
			retries (int, optional): The number of times to retry connecting to the wiki endpoint. Defaults to 3.

		Returns:
			None
		"""
		for i in range(retries):
			try:
				self.site = Site(self.wiki_endpoint, clients_useragent=self.user_agent)
				print(f"MWClient Connected with {self.wiki_endpoint}")
				return	
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
		# Convert sets to lists to avoid TypeError when writing to file
		data = list(data) if isinstance(data, set) else data
		# Write data to file in one go using json.dump
		with open(filename, 'w') as file:
			json.dump(data, file, separators=(',', ':\n'))
		print(f"{filename} saved")

	def wiki_parse(self, title: str) -> Tuple:
		"""
		Parse a wiki page and return a tuple containing the page name and a MWParser Page object.

		Args:
			title (str): The title of the page to parse.

		Returns:
			Tuple[str, mwp.Page]: A tuple containing the page name and the parsed MWParser Page object.
		"""
		page = self.site.pages[title]
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
			{title: [self.site.pages[title], mwp.parse(self.site.pages[title].text())]}
			for title in page_titles
		)

		return self.pages


	def get_sections(self, title: str, page: str) -> List[Dict[str, Any]]:
		"""
		loop through each section, create a paragraph dict including the header name, content, section order, and parent article

		Args:
			title (str): The title of the page to parse.
			page (str): The content of the page to extract sections from.

		Returns:
			List[Dict[str, Any]]: A list of dictionaries containing section information.
		"""
		# Set intro section title to article title (will this cause problems later?)
		current_section: str = title
		# init vars
		sections: List[Dict[str, Any]] = []
		section_order: int = 1
		# loop through each line in the stripped page
		for line in page.strip_code().splitlines():
			if line == '':
				continue  # skip empty lines
			# if header
			if line.startswith(' ') and line.endswith(' '):
				if "Note" in line:
					break  # Notes are just the footnotes. We already captured this in links
				current_section = line.strip()
				section_order = 1
			else:
				# capture paragraph obj
				paragraph_data = {
					"title": current_section,
					"content": line,
					"order": section_order,
					"parent": title
				}
				sections.append(paragraph_data)
				# increment counter
				section_order += 1
		return sections
	
	def clean_wiki_tags(self, page) -> List[str]:
		"""
		Cleans and formats a list of wiki tags into strings for linking in a graph database.
	
		Args:
			page: A MediaWiki page.
	
		Returns:
			A list of cleaned and formatted tag strings.
		"""
		tags = page.filter_templates()
		cleaned_tags: Set[str] = set()
	
		for tag in tags:
			cleaned_tag = tag.replace('{', '').replace('}', '')
	
			# Handle specific tag formats
			if cleaned_tag.startswith(("update", "character", "cite", "quote", "sidequote", "image", "partial", "for", "file")):
				continue
			elif tag.startswith("{{wob ref|"):
				cleaned_tag = f"ref-wob-{cleaned_tag.split('|')[1]}"
			elif tag.startswith("{{book ref|"):
				parts = cleaned_tag.split('|')
				cleaned_tag = "ref-book-" + "-".join(parts[1:])
			elif tag.startswith("{{epigraph ref|"):
				parts = cleaned_tag.split('|')
				cleaned_tag = "ref-epi-" + "-".join(parts[1:])
			elif tag.startswith("{{tag"):
				# Split on pipe (|) and ignore the 'tag' part
				parts = cleaned_tag.split('|')[1:]

				# Handle "cat tag" or "tag|cat=" cases
				if parts[0] == "cat":
					cleaned_tag = parts[2].split('=')[0]  # Get the category name
				elif parts[0] == "army":
					cleaned_tag = parts[1]
				elif "=" in parts[-1]:
					cleaned_tag = parts[0]  # Get the main tag
				else:
					cleaned_tag = '_'.join(parts)
			else:  # Handle other formats
				# Split on pipe (|) and take only the first part
				parts = cleaned_tag.split('|')
				cleaned_tag = parts[0].replace('#', '_').replace(' ', '_').lower()

			if cleaned_tag in {"cat_tag", "cite"}:
				continue

			if cleaned_tag:
				cleaned_tags.add(cleaned_tag.replace("'s", ""))

		return list(cleaned_tags)

	def clean_wiki_links(self, page):
		"""Removes aliases and duplicates from a list of MediaWiki links.

		Args:
			links: A list of strings representing MediaWiki links (e.g., '[[Link]]', '[[Link|Alias]]').

		Returns:
			A new list with unique links, aliases removed.
		"""
		links = page.filter_wikilinks()
		cleaned_links = []
		seen_links = set()  # Track unique links

		for link in links:
			matches = match(r'\[\[(.*?)(?:\|.*?)?\]\]', str(link)) 
			if matches:
				link_text = matches.group(1)  # Extract link text (without alias)
				if link_text not in seen_links:
					cleaned_links.append(link_text)
					seen_links.add(link_text)

		return cleaned_links

	def get_links(self, page):
		out_links = set()
		out_links.update(self.clean_wiki_links(page))
		out_links.update(self.clean_wiki_tags(page))
		result = set()
		for name in out_links:
			# Check if the name is a substring of any other name in the set
			is_redundant = any(name in other_name and name != other_name for other_name in out_links)
			if not is_redundant:
				result.add(name)

		return list(result)

	def process_page(self, page):
		print(f"Processing {page[0]}")
		title = page[0]
		page = page[1]
		if page[0].redirects_to() is not None:
			return {
				"title": title,
				"links": self.get_links(page[1]),
				"sections": None,
				}
		else:
			article = {
					"title": title,
					"links": self.get_links(page[1]),
					"sections": self.get_sections(title, page[1]),
					}
			return article

	def prep_data_graph(self, page_titles):
		self._init_mwclient()
		pages = self.wiki_parse_pages(page_titles)
		for page in pages:
			page = list(page.items())[0]
			prepped_page = self.process_page(page)
			self.data.append(prepped_page)
		self.save_json(self.data)
		return self.data