from mwclient import Site
import mwparserfromhell as mwp
import json
from re import match

class SourceManager:
	def __init__(self, wiki_endpoint="coppermind.net") -> None:
		self.wiki_endpoint=wiki_endpoint
		self.user_agent = "TheataTest (numberticket+cm@proton.me)"
		self.pages = []
		self.data = []

	def _init_mwclient(self, retries=3) -> None:
		for i in range(retries):
			try:
				self.site = Site(self.wiki_endpoint, clients_useragent=self.user_agent)
				print(f"MWClient Connected with {self.wiki_endpoint}")
				return	
			except:
				pass
		print(f"MWClient unable to connect with {self.wiki_endpoint}")
		

	def load_json(self, filename="pages.jsonl"):
		"""Loads data from a JSONLines file, or creates an empty one if it doesn't exist.

		Args:
			filename (str): The name of the JSONLines file. Defaults to "pages.jsonl".

		Returns:
			list: A list of dictionaries loaded from the file, or an empty list if the file didn't exist.
		"""
		data = []
		try:
			with open(filename, 'r') as file:
				for line in file:
					data.append(json.loads(line))
		except FileNotFoundError:
			# File doesn't exist, create an empty one
			with open(filename, 'w') as file:
				pass  # Do nothing, just create the file

		return data

	def save_json(self, data, filename="articles.jsonl"):
		try:
			with open(filename, 'w') as file:
				if isinstance(data, set):
					data = list(data)
				for entry in data:
					file.write(json.dumps(entry) +'\n')
				print(f"{filename} saved")
		except Exception as e:
			print(f"Failed to save {filename} - {e}")

	def wiki_parse(self, title) -> dict:
		"""
		parse wiki page and return wiki code obj from MWParser
		"""
		page = self.site.pages[title]
		return page.name, page

	def wiki_parse_pages(self, page_titles, load=False, update=False):
		"""
		parse multiple pages, append them to existing list, append them to json w/ raw wikicode objs
		"""
		for title in page_titles:
			if load and len(self.pages) > 0:
				self.pages = self.load_json()
			# if not update:
			# 	if len(self.pages) != 0:
			# 		if title in [page['title'] for page in self.pages]: continue
			# ignore cosmere check until after PoC
			title, page = self.wiki_parse(title)
			page_parsed = mwp.parse(page.text())
			self.pages.append({title: [page, page_parsed]})
		return self.pages

	def get_sections(self, title, page):
		"""
		loop through each section, create a paragraph dict including the header name, content, section order, and parent article

		returns dict {title: section header,
					  content: list of paragraphs,
					  header order: int,
					  parent: None (assigned outside of func)}
		"""
		# Set intro section title to article title (will this cause problems later?)
		current_section = title
		# init vars
		sections = []
		section_order = 1
		# loop through each line the stripped page
		for line in page.strip_code().splitlines():
			if line == '': continue # skip empty lines
			# if header
			if line.startswith(' ') and line.endswith(' '):
				if "Note" in line:
					break # Notes are just the footnotes. We already captured this in links
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

	def clean_wiki_tags(self, page):
		"""
		Cleans and formats a list of wiki tags into strings for linking in a graph database.
	
		Args:
			tags: A list of strings representing wiki tags (e.g., '{{tag|Value}}', '{{tag|a|b|c}}').
	
		Returns:
			A list of cleaned and formatted tag strings.
		"""
		tags = page.filter_templates()
		cleaned_tags = set()
	
		for tag in tags:
			cleaned_tag = tag.replace('{', '').replace('}', '')
	
			# Handle specific tag formats
			if cleaned_tag.startswith(("update", "character", "cite", "quote","sidequote", "image", "partial","for", "file")):
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

			if cleaned_tag in ["cat_tag", "cite"]:
				continue

			if cleaned_tag:
				cleaned_tags.add(cleaned_tag.replace("'s",""))

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