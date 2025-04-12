from typing import Optional, Dict, List

from .browser import CoordinateSet, ViewportInfo

""" --------------------------------------------------------------------------------------------------------------------
DOM
-------------------------------------------------------------------------------------------------------------------- """
SelectorMap = dict[int, DOMElementNode]

@dataclass(frozen=False)
class DOMElementNode(DOMBaseNode):
	tag_name: str
	xpath: str
	attributes: Dict[str, str]
	children: List[DOMBaseNode]
	is_interactive: bool = False
	is_top_element: bool = False
	is_in_viewport: bool = False
	shadow_root: bool = False
	highlight_index: Optional[int] = None
	viewport_coordinates: Optional[CoordinateSet] = None
	page_coordinates: Optional[CoordinateSet] = None
	viewport_info: Optional[ViewportInfo] = None
	@cached_property
	def hash(self) -> HashedDomElement: ...
	def get_all_text_till_next_clickable_element(self, max_depth: int = -1) -> str: ...
	@time_execution_sync('--clickable_elements_to_string')
	def clickable_elements_to_string(self, include_attributes: list[str] = []) -> str: ...
	"""Convert the processed DOM content to HTML."""
	def get_file_upload_element(self, check_siblings: bool = True) -> Optional['DOMElementNode']: ...

@dataclass(frozen=False)
class DOMBaseNode:
	is_visible: bool
	parent: Optional['DOMElementNode']

@dataclass
class HashedDomElement:
	"""Hash of the dom element to be used as a unique identifier"""
	branch_path_hash: str
	attributes_hash: str
	xpath_hash: str
