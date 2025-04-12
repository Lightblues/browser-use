
""" --------------------------------------------------------------------------------------------------------------------
Controller: 定义动作空间
	Controller
		包括一些默认的actions
			done
			search_google
			go_to_url
			go_back
			wait
			click_element
			input_text
			switch_tab
			open_tab
			extract_content
			scroll_down
			scroll_up
			send_keys
			scroll_to_text
			get_dropdown_options
			select_dropdown_option
	Registry(Generic[Context]): 动作注册器
		通过 Context 来引入action所需的额外信息
		async def execute_action(...) 是具体调用接口 (调用 action.function), 其包括可选的特殊参数
			browser: BrowserContext 浏览器上下文
			page_extraction_llm: BaseChatModel 执行动作的LLM
			available_file_paths: list[str] 可访问的文件路径
			has_sensitive_data: bool 是否包含敏感数据, 当 `action_name == 'input_text' and sensitive_data` 的时候设置为 True
	RegisteredAction(BaseModel) 定义了动作
		包括 name, description, function, param_model
		通过 prompt_description() 来生成动作的描述 (非 JSON schema)
-------------------------------------------------------------------------------------------------------------------- """
class Controller(Generic[Context]):
	def __init__(self, exclude_actions: list[str] = [], output_model: Optional[Type[BaseModel]] = None):
		self.registry = Registry[Context](exclude_actions)

		"""Register all default browser actions"""
		# Done
		if output_model is not None:
			# Create a new model that extends the output model with success parameter
			class ExtendedOutputModel(output_model):  # type: ignore
				success: bool = True
			@self.registry.action('Complete task - with return text and if the task is finished (success=True) or not yet  completly finished (success=False), because last step is reached', param_model=ExtendedOutputModel)
			async def done(params: ExtendedOutputModel): ...
		else: ...
		# Basic Navigation Actions
		@self.registry.action('Search the query in Google in the current tab, the query should be a search query like humans search in Google, concrete and not vague or super long. More the single most important items. ', param_model=SearchGoogleAction)
		async def search_google(params: SearchGoogleAction, browser: BrowserContext): ...
		@self.registry.action('Navigate to URL in the current tab', param_model=GoToUrlAction)
		async def go_to_url(params: GoToUrlAction, browser: BrowserContext): ...
		@self.registry.action('Go back', param_model=NoParamsAction)
		async def go_back(_: NoParamsAction, browser: BrowserContext): ...
		# wait for x seconds
		@self.registry.action('Wait for x seconds default 3')
		async def wait(seconds: int = 3): ...
		# Element Interaction Actions
		@self.registry.action('Click element', param_model=ClickElementAction)
		async def click_element(params: ClickElementAction, browser: BrowserContext): ...
		@self.registry.action('Input text into a input interactive element', param_model=InputTextAction)
		async def input_text(params: InputTextAction, browser: BrowserContext, has_sensitive_data: bool = False): ...
		# Tab Management Actions
		@self.registry.action('Switch tab', param_model=SwitchTabAction)
		async def switch_tab(params: SwitchTabAction, browser: BrowserContext): ...
		@self.registry.action('Open url in new tab', param_model=OpenTabAction)
		async def open_tab(params: OpenTabAction, browser: BrowserContext): ...
		# Content Actions
		@self.registry.action('Extract page content to retrieve specific information from the page, e.g. all company names, a specifc description, all information about, links with companies in structured format or simply links', param_model=ExtractContentAction)
		async def extract_content(goal: str, browser: BrowserContext, page_extraction_llm: BaseChatModel): ...
		@self.registry.action('Scroll down the page by pixel amount - if no amount is specified, scroll down one page', param_model=ScrollAction)
		async def scroll_down(params: ScrollAction, browser: BrowserContext): ...
		# scroll up
		@self.registry.action('Scroll up the page by pixel amount - if no amount is specified, scroll up one page', param_model=ScrollAction)
		async def scroll_up(params: ScrollAction, browser: BrowserContext): ...
		# send keys
		@self.registry.action('Send strings of special keys like Escape,Backspace, Insert, PageDown, Delete, Enter, Shortcuts such as `Control+o`, `Control+Shift+T` are supported as well. This gets used in keyboard.press. ', param_model=SendKeysAction)
		async def send_keys(params: SendKeysAction, browser: BrowserContext): ...
		@self.registry.action('If you dont find something which you want to interact with, scroll to it')
		async def scroll_to_text(text: str, browser: BrowserContext): ...
		@self.registry.action('Get all options from a native dropdown')
		async def get_dropdown_options(index: int, browser: BrowserContext) -> ActionResult: ...
		@self.registry.action('Select dropdown option for interactive element index by the text of the option you want to select')
		async def select_dropdown_option(index: int, text: str, browser: BrowserContext) -> ActionResult: ...
		"""Select dropdown option by the text of the option you want to select"""

	# Register ---------------------------------------------------------------
	def action(self, description: str, **kwargs):
		"""Decorator for registering custom actions
		@param description: Describe the LLM what the function does (better description == better function calling)
		"""
		return self.registry.action(description, **kwargs)
	# Act --------------------------------------------------------------------
	@time_execution_sync('--act')
	async def act(self, action: ActionModel, browser_context: BrowserContext) -> ActionResult: ...
	"""Execute an action"""

class SearchGoogleAction(BaseModel):
	query: str
class GoToUrlAction(BaseModel):
	url: str
class ClickElementAction(BaseModel):
	index: int
	xpath: Optional[str] = None
class InputTextAction(BaseModel):
	index: int
	text: str
	xpath: Optional[str] = None
class DoneAction(BaseModel):
	text: str
	success: bool
class SwitchTabAction(BaseModel):
	page_id: int
class OpenTabAction(BaseModel):
	url: str
class ScrollAction(BaseModel):
	amount: Optional[int] = None  # The number of pixels to scroll. If None, scroll down/up one page
class SendKeysAction(BaseModel):
	keys: str
class ExtractPageContentAction(BaseModel):
	value: str
class NoParamsAction(BaseModel): ...

# -----------------------------
# Registry
# -----------------------------
class Registry(Generic[Context]):
	"""Service for registering and managing actions"""
	def __init__(self, exclude_actions: list[str] = []):
		self.registry = ActionRegistry()
	def action(self, description: str, param_model: Optional[Type[BaseModel]] = None): ...
	"""Decorator for registering actions"""
	@time_execution_async('--execute_action')
	async def execute_action(self, action_name: str, params: dict, browser: Optional[BrowserContext] = None,
		page_extraction_llm: Optional[BaseChatModel] = None, sensitive_data: Optional[Dict[str, str]] = None, available_file_paths: Optional[list[str]] = None,
		context: Context | None = None,
	) -> Any: ...
	@time_execution_sync('--create_action_model')
	def create_action_model(self, include_actions: Optional[list[str]] = None) -> Type[ActionModel]: ...
	def get_prompt_description(self) -> str:
		"""Get a description of all actions for the prompt"""
		return self.registry.get_prompt_description()

class ActionRegistry(BaseModel):
	"""Model representing the action registry"""
	actions: Dict[str, RegisteredAction] = {}
	def get_prompt_description(self) -> str: ...
	"""Get a description of all actions for the prompt"""

class RegisteredAction(BaseModel):
	"""Model for a registered action"""
	name: str
	description: str
	function: Callable
	param_model: Type[BaseModel]
	def prompt_description(self) -> str: ...


class ActionModel(BaseModel):
	"""Base model for dynamically created action models"""
	def get_index(self) -> int | None: ...
	def set_index(self, index: int): ...
