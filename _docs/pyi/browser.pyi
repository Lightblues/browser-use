from typing import Any, Optional
from pydantic import BaseModel
from dataclasses import dataclass, field
from playwright.async_api import Playwright, Browser as PlaywrightBrowser, BrowserContext as PlaywrightBrowserContext, ElementHandle, Page

from .dom import DOMElementNode, CoordinateSet, ViewportInfo

""" --------------------------------------------------------------------------------------------------------------------
Browser
-------------------------------------------------------------------------------------------------------------------- """
@dataclass
class BrowserStateHistory:
	url: str
	title: str
	tabs: list[TabInfo]
	interacted_element: list[DOMHistoryElement | None] | list[None]
	screenshot: Optional[str] = None
	def to_dict(self) -> dict[str, Any]: ...

class TabInfo(BaseModel):
	"""Represents information about a browser tab"""
	page_id: int
	url: str
	title: str

@dataclass
class DOMHistoryElement:
	tag_name: str
	xpath: str
	highlight_index: Optional[int]
	entire_parent_branch_path: list[str]
	attributes: dict[str, str]
	shadow_root: bool = False
	css_selector: Optional[str] = None
	page_coordinates: Optional[CoordinateSet] = None
	viewport_coordinates: Optional[CoordinateSet] = None
	viewport_info: Optional[ViewportInfo] = None
	def to_dict(self) -> dict: ...

class Coordinates(BaseModel):
	x: int
	y: int

class CoordinateSet(BaseModel):
	top_left: Coordinates
	top_right: Coordinates
	bottom_left: Coordinates
	bottom_right: Coordinates
	center: Coordinates
	width: int
	height: int

class ViewportInfo(BaseModel):
	scroll_x: int
	scroll_y: int
	width: int
	height: int


# @singleton: TODO - think about id singleton makes sense here
# @dev By default this is a singleton, but you can create multiple instances if you need to.
class Browser:
	"""
	Playwright browser on steroids.

	This is persistant browser factory that can spawn multiple browser contexts.
	It is recommended to use only one instance of Browser per your application (RAM usage will grow otherwise).
	"""
	def __init__(self, config: BrowserConfig = BrowserConfig()):
		self.config = config
		self.playwright: Playwright | None = None
		self.playwright_browser: PlaywrightBrowser | None = None


	async def new_context(self, config: BrowserContextConfig = BrowserContextConfig()) -> BrowserContext: ...
	async def get_playwright_browser(self) -> PlaywrightBrowser: ...
	@time_execution_async('--init (browser)')
	async def _init(self): ...
	async def _setup_cdp(self, playwright: Playwright) -> PlaywrightBrowser: ...
	async def _setup_wss(self, playwright: Playwright) -> PlaywrightBrowser: ...
	async def _setup_browser_with_instance(self, playwright: Playwright) -> PlaywrightBrowser: ...
	async def _setup_standard_browser(self, playwright: Playwright) -> PlaywrightBrowser: ...
	async def _setup_browser(self, playwright: Playwright) -> PlaywrightBrowser: ...
	async def close(self): ...

@dataclass
class BrowserConfig:
	headless: bool = False
	disable_security: bool = True
	extra_chromium_args: list[str] = field(default_factory=list)
	chrome_instance_path: str | None = None
	wss_url: str | None = None
	cdp_url: str | None = None

	proxy: ProxySettings | None = field(default=None)
	new_context_config: BrowserContextConfig = field(default_factory=BrowserContextConfig)


class ProxySettings(TypedDict, total=False):
    server: str
    bypass: Optional[str]
    username: Optional[str]
    password: Optional[str]

class BrowserContext:
	async def get_session(self) -> BrowserSession: ...
	async def get_current_page(self) -> Page: ...
	async def navigate_to(self, url: str): ...
	async def refresh_page(self): ...
	async def go_back(self): ...
	async def go_forward(self): ...
	async def close_current_tab(self): ...
	async def get_page_html(self) -> str: ...
	async def execute_javascript(self, script: str): ...
	@time_execution_sync('--get_state')  # This decorator might need to be updated to handle async
	async def get_state(self) -> BrowserState: ...
	async def get_selector_map(self) -> SelectorMap: ...
	async def get_element_by_index(self, index: int) -> ElementHandle | None: ...
	async def get_dom_element_by_index(self, index: int) -> DOMElementNode: ...
	async def save_cookies(self): ...
	async def is_file_uploader(self, element_node: DOMElementNode, max_depth: int = 3, current_depth: int = 0) -> bool: ...
	async def get_scroll_info(self, page: Page) -> tuple[int, int]: ...
	async def reset_context(self): ...

@dataclass
class BrowserContextConfig:
	cookies_file: str | None = None
	minimum_wait_page_load_time: float = 0.25
	wait_for_network_idle_page_load_time: float = 0.5
	maximum_wait_page_load_time: float = 5
	wait_between_actions: float = 0.5

	disable_security: bool = True

	browser_window_size: BrowserContextWindowSize = field(default_factory=lambda: {'width': 1280, 'height': 1100})
	no_viewport: Optional[bool] = None

	save_recording_path: str | None = None
	save_downloads_path: str | None = None
	trace_path: str | None = None
	locale: str | None = None
	user_agent: str = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36  (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36'

	highlight_elements: bool = True
	viewport_expansion: int = 500
	allowed_domains: list[str] | None = None
	include_dynamic_attributes: bool = True

class BrowserContextWindowSize(TypedDict):
	width: int
	height: int

@dataclass
class BrowserState(DOMState):
	url: str
	title: str
	tabs: list[TabInfo]
	screenshot: Optional[str] = None
	pixels_above: int = 0
	pixels_below: int = 0
	browser_errors: list[str] = field(default_factory=list)

@dataclass
class BrowserSession:
	context: PlaywrightBrowserContext
	cached_state: BrowserState | None

class BrowserContext:
	async def get_session(self) -> BrowserSession: ...
	async def get_current_page(self) -> Page: ...
	async def navigate_to(self, url: str): ...
	async def refresh_page(self): ...
	async def go_back(self): ...
	async def go_forward(self): ...
	async def close_current_tab(self): ...
	async def get_page_html(self) -> str: ...
	async def execute_javascript(self, script: str): ...
	async def get_page_structure(self) -> str: ...
	@time_execution_sync('--get_state')  # This decorator might need to be updated to handle async
	async def get_state(self) -> BrowserState: ...
	# Browser Actions
	@time_execution_async('--take_screenshot')
	async def take_screenshot(self, full_page: bool = False) -> str: ...
	@time_execution_async('--remove_highlights')
	async def remove_highlights(self): ...
	@time_execution_async('--get_locate_element')
	# User Actions
	async def get_locate_element(self, element: DOMElementNode) -> Optional[ElementHandle]: ...
	@time_execution_async('--get_locate_element_by_xpath')
	async def get_locate_element_by_xpath(self, xpath: str) -> Optional[ElementHandle]: ...
	@time_execution_async('--get_locate_element_by_css_selector')
	async def get_locate_element_by_css_selector(self, css_selector: str) -> Optional[ElementHandle]: ...
	@time_execution_async('--get_locate_element_by_text')
	async def get_locate_element_by_text(self, text: str, nth: Optional[int] = 0, element_type: Optional[str] = None) -> Optional[ElementHandle]: ...
	@time_execution_async('--get_tabs_info')
	async def get_tabs_info(self) -> list[TabInfo]: ...
	@time_execution_async('--switch_to_tab')
	async def switch_to_tab(self, page_id: int) -> None: ...
	@time_execution_async('--create_new_tab')
	async def create_new_tab(self, url: str | None = None) -> None: ...
	# Helper methods for easier access to the DOM
	async def get_element_by_index(self, index: int) -> ElementHandle | None: ...
	async def get_dom_element_by_index(self, index: int) -> DOMElementNode: ...
	async def save_cookies(self): ...
	async def is_file_uploader(self, element_node: DOMElementNode, max_depth: int = 3, current_depth: int = 0) -> bool: ...
	async def get_scroll_info(self, page: Page) -> tuple[int, int]: ...
	async def reset_context(self): ...
	async def wait_for_element(self, selector: str, timeout: float) -> None: ...

