from typing import Optional, Dict, List

from .browser import CoordinateSet, ViewportInfo

""" --------------------------------------------------------------------------------------------------------------------
DOM
1. 方案: 网页结构构建为一个 DOM tree
	包括 DOMElementNode, DOMTextNode 两类
2. 最终生成 DOMState, 包括 DOM tree, 还有标记为可交互的 index map (SelectorMap)

---
	DOMElementNode
		.clickable_elements_to_string(self, include_attributes: list[str] = []) -> str: 构建可交互元素的字符串表示. 线性展开树结构
	DomService
		.async def get_clickable_elements(self, highlight_elements: bool = True, focus_element: int = -1, viewport_expansion: int = 0) -> 'DOMState':
-------------------------------------------------------------------------------------------------------------------- """
# dom/views.py
@dataclass
class DOMState:
	element_tree: DOMElementNode
	selector_map: SelectorMap

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


	def clickable_elements_to_string(self, include_attributes: list[str] = []) -> str:
		"""Convert the processed DOM content to HTML."""
		formatted_text = []
		def process_node(node: DOMBaseNode, depth: int) -> None:
			if isinstance(node, DOMElementNode):
				if node.highlight_index is not None:
					formatted_text.append(line)
				for child in node.children:
					process_node(child, depth + 1)
			elif isinstance(node, DOMTextNode):
				formatted_text.append(f'{node.text}')
		process_node(self, 0)
		return '\n'.join(formatted_text)

	def get_file_upload_element(self, check_siblings: bool = True) -> Optional['DOMElementNode']: ...

class DOMTextNode(DOMBaseNode):
	text: str
	type: str = 'TEXT_NODE'

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



# dom/service.py
from playwright.async_api import Page
from importlib import resources

@dataclass
class ViewportInfo:
	width: int
	height: int

class DomService:
	def __init__(self, page: 'Page'):
		self.page = page
		self.xpath_cache = {}
		self.js_code = resources.files('browser_use.dom').joinpath('buildDomTree.js').read_text()

	async def get_clickable_elements(self, highlight_elements: bool = True, focus_element: int = -1, viewport_expansion: int = 0) -> 'DOMState':
		element_tree, selector_map = await self._build_dom_tree(highlight_elements, focus_element, viewport_expansion)
		return DOMState(element_tree=element_tree, selector_map=selector_map)

	async def _build_dom_tree(self, highlight_elements: bool, focus_element: int, viewport_expansion: int) -> tuple[DOMElementNode, SelectorMap]:
		args = {
			'doHighlightElements': highlight_elements,
			'focusHighlightIndex': focus_element,
			'viewportExpansion': viewport_expansion,
			'debugMode': debug_mode,
		}
		eval_page: dict = await self.page.evaluate(self.js_code, args)

		js_node_map = eval_page['map']
		selector_map = {}
		for id, node_data in js_node_map.items():
			node, children_ids = self._parse_node(node_data)
			if isinstance(node, DOMElementNode) and node.highlight_index is not None:
				selector_map[node.highlight_index] = node

		return html_to_dict, selector_map

	def _parse_node(self, node_data: dict) -> tuple[Optional[DOMBaseNode], list[int]]:
		if node_data.get('type') == 'TEXT_NODE':
			text_node = DOMTextNode(...)
			return text_node, []

		element_node = DOMElementNode(...)
		children_ids = node_data.get('children', [])
		return element_node, children_ids


