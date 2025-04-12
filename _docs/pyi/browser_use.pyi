""" 
version: 0.1.40
url: https://github.com/browser-use/browser-use/blob/0.1.40/browser_use
"""

import uuid, logging, asyncio, re
from typing import Any, Awaitable, Callable, Dict, Generic, List, Optional, Type, TypeVar, TYPE_CHECKING, Literal, ParamSpec, Coroutine, TypedDict
from dataclasses import dataclass, field
from pathlib import Path
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage, AIMessage
from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger(__name__)

""" --------------------------------------------------------------------------------------------------------------------
Agent
	AgentOutput: 定义了agent的输出, 包括:
		AgentBrain: evaluation_previous_goal, memory, next_goal 三部分
		action: list[ActionModel]: 动作列表
	AgentState: 包含agent的完整状态, 包括:
		history: AgentHistoryList: 包含完整信息
		message_manager_state: MessageManagerState: 维护LLM相关信息
	Agent: 智能体, 包括:
		浏览器相关, 包括 browser, browser_context
		controller: 定义动作空间
		state: AgentState: 包含agent的完整状态
		_message_manager: MessageManager: 消息管理器
	AgentSettings: 包含agent的配置
		ToolCallingMethod: 工具调用方式, 包括 'function_calling', 'json_mode', 'raw', 'auto'
			自动解析: deepseek-r1 -> raw; openai -> function_calling; google -> None
			raw: 对于不支持工具调用的LLM, 将工具定义写入messages中! 
		message_context? LLM不支持
			最终作用的是 MessageManagerSettings.message_context
			当 `.tool_calling_method == 'raw'` 时, 将工具定义添加到 messages 中, 参见 MessageManager._init_messages()
	MessageManager: 消息管理器
		_init_messages(): 定义了初始化配置, 包括:
			1. system prompt
			2. context (可选): 'Context for the task: {xxx}'
			3. task: 'Your ultimate task is: {self.task}. If you achieved your ultimate task, stop everything and use the done action in the next step to complete the task. If not, continue as usual.'
			4. sensitive data (可选): 'Here are placeholders for sensitve data: {xxx}. To use them, write <secret>the placeholder name</secret>'
			5. example output: 'Example output: xxx' + 工具调用的case
			6. task memory: '[Your task history memory starts here]'
			7. file paths (可选): 'Here are file paths you can use: {xxx}'
-------------------------------------------------------------------------------------------------------------------- """
# -----------------------------
# Prompt
# -----------------------------
class SystemPrompt:
	def __init__(self, action_description: str, max_actions_per_step: int = 10):
		self.default_action_description = action_description
		self.max_actions_per_step = max_actions_per_step
		self.prompt_template = ...
	def get_system_message(self) -> SystemMessage: ...

class AgentMessagePrompt:
	def get_user_message(self, use_vision: bool = True) -> HumanMessage: ...
class PlannerPrompt(SystemPrompt):
	def get_system_message(self) -> SystemMessage: ...

# -----------------------------
# Agent
# -----------------------------
Context = TypeVar('Context')

class Agent(Generic[Context]):
	@time_execution_sync('--init (agent)')
	def __init__(self, 
		task: str, llm: BaseChatModel, 
		browser: Browser=None, browser_context: BrowserContext=None, controller: Controller[Context]=Controller(),
		sensitive_data: Optional[Dict[str, str]] = None, initial_actions: Optional[List[Dict[str, Dict[str, Any]]]] = None,
		injected_agent_state: Optional[AgentState] = None, context: Optional[Context] = None
	):
		# Core components
		self.task = task  # 输入的任务
		self.llm = llm  # LLM
		self.controller = controller  # 控制器
		self.sensitive_data = sensitive_data  # 敏感数据
		self.settings = AgentSettings(...)
		# Initialize state
		self.state = injected_agent_state or AgentState()  # agent 的完整信息
		# Action setup
		self._setup_action_models()  # 构建 self.ActionModel/AgentOutput
		self._set_browser_use_version_and_source()
		self.initial_actions = self._convert_initial_actions(initial_actions) if initial_actions else None
		# Model setup
		self._set_model_names()  # 设置模型名称 self.model_name, self.planner_model_name
		# for models without tool calling, add available actions to context
		self.available_actions = self.controller.registry.get_prompt_description()  # 从控制器获取可用动作的描述
		self.tool_calling_method = self._set_tool_calling_method()
		self.settings.message_context = self._set_message_context()
		# Initialize message manager with state
		self._message_manager = MessageManager(  # 消息管理器
			task=task,
			system_prompt=self.settings.system_prompt_class(),
			state=self.state.message_manager_state,
		)
		# Browser setup
		self.browser = browser if browser is not None else (None if browser_context else Browser())  # 浏览器
		self.browser_context = BrowserContext(browser=self.browser, config=self.browser.config.new_context_config)  # 浏览器上下文
		# Context
		self.context = context  # 提供给 self.controller.action(..., context=self.context)

	# @observe(name='agent.run', ignore_output=True)
	@time_execution_async('--run (agent)')
	async def run(self, max_steps: int = 100) -> AgentHistoryList:
		"""Execute the task with maximum number of steps"""
		try:
			# Execute initial actions if provided
			if self.initial_actions:
				result = await self.multi_act(self.initial_actions, check_for_new_elements=False)
				self.state.last_result = result
			for step in range(max_steps):
				# Check if we should stop due to too many failures
				if self.state.consecutive_failures >= self.settings.max_failures: break
				# Check control flags before each step
				if self.state.stopped: break
				while self.state.paused:
					await asyncio.sleep(0.2)  # Small delay to prevent CPU spinning
				step_info = AgentStepInfo(step_number=step, max_steps=max_steps)
				await self.step(step_info)
				if self.state.history.is_done():
					break
			else:
				logger.info('❌ Failed to complete task in maximum steps')
		finally: ...

	# @observe(name='agent.step', ignore_output=True, ignore_input=True)
	@time_execution_async('--step (agent)')
	async def step(self, step_info: Optional[AgentStepInfo] = None) -> None:
		"""Execute one step of the task"""
		try:
			# 1. 增加状态信息, 构建给LLM的 input_messages (context!)
			state = await self.browser_context.get_state()
			self._message_manager.add_state_message(state, self.state.last_result, step_info, self.settings.use_vision)
			# Run planner at specified intervals if planner is configured
			if self.settings.planner_llm and self.state.n_steps % self.settings.planner_interval == 0:
				plan = await self._run_planner()
				# add plan before last state message
				self._message_manager.add_plan(plan, position=-1)

			# 2. 调用模型, 保存模型调用结果 (one step)
			input_messages = self._message_manager.get_messages()
			try:
				model_output = await self.get_next_action(input_messages)
				self.state.n_steps += 1
				# ... 注意这里agent的逻辑, 会将第一步的state从history中删除, 仅保留结果
				self._message_manager._remove_last_state_message()  # we dont want the whole state in the chat history
				await self._raise_if_stopped_or_paused()
				self._message_manager.add_model_output(model_output)
			except Exception as e:
				# model call failed, remove last state message from history
				self._message_manager._remove_last_state_message()
				raise e
			# 3. 执行动作, 保存结果
			result: list[ActionResult] = await self.multi_act(model_output.action)
			self.state.last_result = result  # 工具结果将用到下一次state构建!
			self.state.consecutive_failures = 0
		finally: ...

	@time_execution_async('--get_next_action (agent)')
	async def get_next_action(self, input_messages: list[BaseMessage]) -> AgentOutput:
		"""Get next action from LLM based on current state"""
		input_messages = self._convert_input_messages(input_messages)
		if self.tool_calling_method == 'raw':
			output = self.llm.invoke(input_messages)
			output.content = self._remove_think_tags(str(output.content))
			parsed_json = extract_json_from_model_output(output.content)
			parsed = self.AgentOutput(**parsed_json)
		else:
			structured_llm = self.llm.with_structured_output(self.AgentOutput, include_raw=True, method=self.tool_calling_method)
			response: dict[str, Any] = await structured_llm.ainvoke(input_messages)  # type: ignore
			parsed: AgentOutput | None = response['parsed']
		return parsed

	async def _run_planner(self) -> Optional[str]:
		"""Run the planner to analyze state and suggest next steps"""
		# Create planner message history using full message history
		planner_messages = [
			PlannerPrompt(self.controller.registry.get_prompt_description()).get_system_message(),
			*self._message_manager.get_messages()[1:],  # Use full message history except the first
		]
		planner_messages = convert_input_messages(planner_messages, self.planner_model_name)
		response = await self.settings.planner_llm.ainvoke(planner_messages)
		plan = str(response.content)
		return plan

	# @observe(name='controller.multi_act')
	@time_execution_async('--multi-act (agent)')
	async def multi_act(self, actions: list[ActionModel], check_for_new_elements: bool = True) -> list[ActionResult]:
		"""Execute multiple actions"""

	def _set_tool_calling_method(self) -> Optional[ToolCallingMethod]:
		tool_calling_method = self.settings.tool_calling_method
		if tool_calling_method == 'auto': ...

	def _set_message_context(self) -> str | None:  # 对于不支持工具调用的LLM, 将动作添加到消息中
		if self.tool_calling_method == 'raw':
			if self.settings.message_context:
				self.settings.message_context += f'\n\nAvailable actions: {self.available_actions}'
			else:
				self.settings.message_context = f'Available actions: {self.available_actions}'
		return self.settings.message_context

	def _setup_action_models(self) -> None:
		"""Setup dynamic action models from controller's registry"""
		self.ActionModel = self.controller.registry.create_action_model()
		# Create output model with the dynamic actions
		self.AgentOutput = AgentOutput.type_with_custom_actions(self.ActionModel)

	def _set_model_names(self) -> None:
		self.chat_model_library = self.llm.__class__.__name__
		self.model_name = 'Unknown'
		if hasattr(self.llm, 'model_name'):
			self.model_name = self.llm.model_name  # type: ignore
		elif hasattr(self.llm, 'model'):
			self.model_name = self.llm.model  # type: ignore
		if self.settings.planner_llm: ... # 同上
		else:
			self.planner_model_name = None

	async def _raise_if_stopped_or_paused(self) -> None:
		if self.state.stopped or self.state.paused:
			raise InterruptedError
	def _convert_input_messages(self, input_messages: list[BaseMessage]) -> list[BaseMessage]:
		"""Convert input messages to the correct format""" # 针对R1类
	THINK_TAGS = re.compile(r'<think>.*?</think>', re.DOTALL)
	def _remove_think_tags(self, text: str) -> str:
		"""Remove think tags from text"""
		return re.sub(self.THINK_TAGS, '', text)
	def _convert_initial_actions(self, actions: List[Dict[str, Dict[str, Any]]]) -> List[ActionModel]:
		"""Convert dictionary-based actions to ActionModel instances"""
	def _set_browser_use_version_and_source(self) -> None:
		"""Get the version and source of the browser-use package (git or pip in a nutshell)"""

# -----------------------------
# AgentState. history包含完整信息; message_manager_state 维护LLM相关信息
# -----------------------------
class AgentState(BaseModel):
	"""Holds all state information for an Agent"""
	agent_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
	n_steps: int = 1
	consecutive_failures: int = 0
	last_result: Optional[List['ActionResult']] = None
	history: AgentHistoryList = Field(default_factory=lambda: AgentHistoryList(history=[]))  # 包括浏览器的完整信息
	last_plan: Optional[str] = None
	paused: bool = False
	stopped: bool = False
	message_manager_state: MessageManagerState = Field(default_factory=MessageManagerState)  # 管理和LLM的消息

@dataclass
class AgentStepInfo:
	step_number: int
	max_steps: int
	def is_last_step(self) -> bool: ...

# -----------------------------
# MessageManager
# -----------------------------
class MessageManager:
	def __init__(
		self,
		task: str,
		system_message: SystemMessage,
		settings: MessageManagerSettings = MessageManagerSettings(),
		state: MessageManagerState = MessageManagerState(),
	):
		self.task = task
		self.system_prompt = system_message
		self.settings = settings
		self.state = state
		# Only initialize messages if state is empty
		if len(self.state.history.messages) == 0:
			self._init_messages()

	def _init_messages(self) -> None:
		"""Initialize the message history with system message, context, task, and other initial messages"""
		# 1. SP
		self._add_message_with_tokens(self.system_prompt)
		# 2. context
		if self.settings.message_context:
			context_message = HumanMessage(content='Context for the task' + self.settings.message_context)
			self._add_message_with_tokens(context_message)
		# 3. task
		task_message = HumanMessage(content=f'Your ultimate task is: """{self.task}""". If you achieved your ultimate task, stop everything and use the done action in the next step to complete the task. If not, continue as usual.')
		self._add_message_with_tokens(task_message)
		# 4. sensitive data
		if self.settings.sensitive_data:
			info = f'Here are placeholders for sensitve data: {list(self.settings.sensitive_data.keys())}'
			info += 'To use them, write <secret>the placeholder name</secret>'
			info_message = HumanMessage(content=info)
			self._add_message_with_tokens(info_message)
		# 5. example
		placeholder_message = HumanMessage(content='Example output:')
		self._add_message_with_tokens(placeholder_message)
		tool_calls = [
			{
				'name': 'AgentOutput',
				'args': {
					'current_state': {
						'evaluation_previous_goal': 'Success - I opend the first page',
						'memory': 'Starting with the new task. I have completed 1/10 steps',
						'next_goal': 'Click on company a',
					},
					'action': [{'click_element': {'index': 0}}],
				},
				'id': str(self.state.tool_id),
				'type': 'tool_call',
			}
		]
		example_tool_call = AIMessage(context='', tool_calls=tool_calls)
		self._add_message_with_tokens(example_tool_call)
		self.add_tool_message(content='Browser started')
		# 6. task history
		placeholder_message = HumanMessage(content='[Your task history memory starts here]')
		self._add_message_with_tokens(placeholder_message)
		# 7. file paths
		if self.settings.available_file_paths:
			filepaths_msg = HumanMessage(content=f'Here are file paths you can use: {self.settings.available_file_paths}')
			self._add_message_with_tokens(filepaths_msg)
	def _add_message_with_tokens(self, message: BaseMessage, position: int | None = None) -> None: ...
	
	def add_new_task(self, new_task: str) -> None:
		content = f'Your new ultimate task is: """{new_task}""". Take the previous context into account and finish your new ultimate task. '
		msg = HumanMessage(content=content)
		self._add_message_with_tokens(msg)
		self.task = new_task
	@time_execution_sync('--add_state_message')
	def add_state_message(self, state: BrowserState, result: Optional[list[ActionResult]]=None, step_info: Optional[AgentStepInfo] = None, use_vision=True) -> None: ...
	def add_model_output(self, model_output: AgentOutput) -> None: ...
	def add_plan(self, plan: Optional[str], position: int | None = None) -> None: ...
	@time_execution_sync('--get_messages')
	def get_messages(self) -> List[BaseMessage]: ...
	@time_execution_sync('--filter_sensitive_data')
	def _filter_sensitive_data(self, message: BaseMessage) -> BaseMessage: ...
	def cut_messages(self) -> None: ...
	def add_tool_message(self, content: str) -> None: ...

	def _remove_last_state_message(self) -> None:
		self.state.history.remove_last_state_message()

class MessageManagerSettings(BaseModel):
	max_input_tokens: int = 128000
	estimated_characters_per_token: int = 3
	image_tokens: int = 800
	include_attributes: list[str] = []
	message_context: Optional[str] = None
	sensitive_data: Optional[Dict[str, str]] = None
	available_file_paths: Optional[List[str]] = None

class MessageHistory(BaseModel):
	"""History of messages with metadata"""
	messages: list[ManagedMessage] = Field(default_factory=list)
	current_tokens: int = 0
	def add_message(self, message: BaseMessage, metadata: MessageMetadata, position: int | None = None) -> None: ...
	def add_model_output(self, output: 'AgentOutput') -> None: ...
	def get_messages(self) -> list[BaseMessage]: ...
	def get_total_tokens(self) -> int: ...
	def remove_oldest_message(self) -> None: ...
	def remove_last_state_message(self) -> None: ...

class MessageManagerState(BaseModel):
	"""Holds the state for MessageManager"""
	history: MessageHistory = Field(default_factory=MessageHistory)
	tool_id: int = 1

class MessageMetadata(BaseModel):
	tokens: int = 0

class ManagedMessage(BaseModel):
	"""A message with its metadata"""
	message: BaseMessage
	metadata: MessageMetadata = Field(default_factory=MessageMetadata)
	# https://github.com/pydantic/pydantic/discussions/7558
	@model_serializer(mode='wrap')
	def to_json(self, original_dump):
		"""Returns the JSON representation of the model.
		It uses langchain's `dumps` function to serialize the `message`
		property before encoding the overall dict with json.dumps."""

# -----------------------------
# AgentSettings
# -----------------------------
class AgentSettings(BaseModel):
	use_vision: bool = True
	use_vision_for_planner: bool = False
	save_conversation_path: Optional[str] = None
	save_conversation_path_encoding: Optional[str] = 'utf-8'
	max_failures: int = 3
	retry_delay: int = 10
	system_prompt_class: Type[SystemPrompt] = SystemPrompt
	max_input_tokens: int = 128000
	validate_output: bool = False
	message_context: Optional[str] = None
	generate_gif: bool | str = False
	available_file_paths: Optional[list[str]] = None
	include_attributes: list[str] = ["title", "type", "name", "role", "tabindex", "aria-label", "placeholder", "value", "alt", "aria-expanded"]
	max_actions_per_step: int = 10
	tool_calling_method: Optional[ToolCallingMethod] = 'auto'
	page_extraction_llm: Optional[BaseChatModel] = None
	planner_llm: Optional[BaseChatModel] = None
	planner_interval: int = 1  # Run planner every N steps

ToolCallingMethod = Literal['function_calling', 'json_mode', 'raw', 'auto']

# -----------------------------
# AgentOutput & Action
# -----------------------------
class AgentOutput(BaseModel):
	"""Output model for agent"""
	current_state: AgentBrain
	action: list[ActionModel] = Field(...)
	@staticmethod
	def type_with_custom_actions(custom_actions: Type[ActionModel]) -> Type['AgentOutput']: ...
	"""Extend actions with custom actions"""

class AgentBrain(BaseModel):
	"""Current state of the agent"""
	evaluation_previous_goal: str
	memory: str
	next_goal: str

class ActionResult(BaseModel):
	"""Result of executing an action"""
	is_done: Optional[bool] = False
	success: Optional[bool] = None
	extracted_content: Optional[str] = None
	error: Optional[str] = None
	include_in_memory: bool = False  # whether to include in past messages as context or not

# -----------------------------
# AgentHistory: Agent日志, +浏览器状态
# -----------------------------
class AgentHistoryList(BaseModel):
	"""List of agent history items"""
	history: list[AgentHistory]
	def total_duration_seconds(self) -> float: ...
	def total_input_tokens(self) -> int: ...
	def input_token_usage(self) -> list[int]: ...
	def save_to_file(self, filepath: str | Path) -> None: ...
	@classmethod
	def load_from_file(cls, filepath: str | Path, output_model: Type[AgentOutput]) -> 'AgentHistoryList': ...
	def last_action(self) -> None | dict: ...
	def errors(self) -> list[str | None]: ...
	def final_result(self) -> None | str: ...
	def is_done(self) -> bool: ...
	def is_successful(self) -> bool | None: ...
	def has_errors(self) -> bool: ...
	def urls(self) -> list[str | None]: ...
	def screenshots(self) -> list[str | None]: ...
	def action_names(self) -> list[str]: ...
	def model_thoughts(self) -> list[AgentBrain]: ...
	def model_outputs(self) -> list[AgentOutput]: ...
	def model_actions(self) -> list[dict]: ...
	def action_results(self) -> list[ActionResult]: ...
	def extracted_content(self) -> list[str]: ...
	def model_actions_filtered(self, include: list[str] = []) -> list[dict]: ...
	def number_of_steps(self) -> int: ...

class AgentHistory(BaseModel):
	"""History item for agent actions"""
	model_output: AgentOutput | None
	result: list[ActionResult]
	state: BrowserStateHistory  # 浏览器状态
	metadata: Optional[StepMetadata] = None  # 步骤元数据
	
	@staticmethod
	def get_interacted_element(model_output: AgentOutput, selector_map: SelectorMap) -> list[DOMHistoryElement | None]: ...
	def model_dump(self, **kwargs) -> Dict[str, Any]: ...
	"""Custom serialization handling circular references"""

class StepMetadata(BaseModel):
	"""Metadata for a single step including timing and token information"""
	step_start_time: float
	step_end_time: float
	input_tokens: int  # Approximate tokens from message manager for this step
	step_number: int
	@property
	def duration_seconds(self) -> float: ...


""" --------------------------------------------------------------------------------------------------------------------
utils
-------------------------------------------------------------------------------------------------------------------- """
# Define generic type variables for return type and parameters
R = TypeVar('R')
P = ParamSpec('P')

def time_execution_sync(additional_text: str = '') -> Callable[[Callable[P, R]], Callable[P, R]]: ...
def time_execution_async(additional_text: str = '',) -> Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]: ...
def singleton(cls): ...

def extract_json_from_model_output(content: str) -> dict:
	"""Extract JSON from model output, handling both plain JSON and code-block-wrapped JSON."""
def convert_input_messages(input_messages: list[BaseMessage], model_name: Optional[str]) -> list[BaseMessage]:
	"""Convert input messages to a format that is compatible with the planner model"""
	if model_name == 'deepseek-reasoner' or model_name.startswith('deepseek-r1'):
		converted_input_messages = _convert_messages_for_non_function_calling_models(input_messages)
		merged_input_messages = _merge_successive_messages(converted_input_messages, HumanMessage)
		merged_input_messages = _merge_successive_messages(merged_input_messages, AIMessage)
		return merged_input_messages
	return input_messages
def _convert_messages_for_non_function_calling_models(input_messages: list[BaseMessage]) -> list[BaseMessage]:
	"""Convert messages for non-function-calling models"""
def _merge_successive_messages(messages: list[BaseMessage], class_to_merge: Type[BaseMessage]) -> list[BaseMessage]:
	"""Some models like deepseek-reasoner dont allow multiple human messages in a row. This function merges them into one."""
