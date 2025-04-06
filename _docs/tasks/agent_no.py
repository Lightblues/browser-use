""" 
2025-03-14
自定义 BU 的各个组件, 去除浏览器相关逻辑 (仅保留核心逻辑)

NOTE: 适用于 0.1.40, 新版取消了 SystemPrompt 接口, 暂时无法跑通
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import platform
import textwrap
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
	BaseMessage,
	SystemMessage,
)
from lmnr import observe
from openai import RateLimitError
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ValidationError

from browser_use.agent.message_manager.service import MessageManager
from browser_use.agent.prompts import AgentMessagePrompt, SystemPrompt
from browser_use.agent.views import (
	ActionResult,
	AgentError,
	AgentHistory,
	AgentHistoryList,
	AgentOutput,
	AgentStepInfo,
)
from browser_use.browser.browser import Browser
from browser_use.browser.context import BrowserContext
from browser_use.browser.views import BrowserState, BrowserStateHistory
from browser_use.controller.registry.views import ActionModel
from browser_use.controller.service import Controller
from browser_use.dom.history_tree_processor.service import (
	DOMHistoryElement,
	HistoryTreeProcessor,
)
from browser_use.telemetry.service import ProductTelemetry
from browser_use.telemetry.views import (
	AgentEndTelemetryEvent,
	AgentRunTelemetryEvent,
	AgentStepTelemetryEvent,
)
from browser_use.utils import time_execution_async, time_execution_sync
from browser_use import Agent, Controller, SystemPrompt
load_dotenv()
logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from browser_use.controller.registry.service import Registry
from browser_use.controller.views import (
	ClickElementAction,
	DoneAction,
	ExtractPageContentAction,
	GoToUrlAction,
	InputTextAction,
	NoParamsAction,
	OpenTabAction,
	ScrollAction,
	SearchGoogleAction,
	SendKeysAction,
	SwitchTabAction,
)



class CustomizedAgentMessagePrompt(AgentMessagePrompt):
	def __init__(
		self,
		# state: BrowserState,
		result: Optional[List[ActionResult]] = None,
		include_attributes: list[str] = [],
		max_error_length: int = 400,
		step_info: Optional[AgentStepInfo] = None,
	):
		# self.state = state
		self.result = result
		self.max_error_length = max_error_length
		self.include_attributes = include_attributes
		self.step_info = step_info

	def get_user_message(self) -> HumanMessage:
		if self.step_info:
			step_info_description = f'Current step: {self.step_info.step_number + 1}/{self.step_info.max_steps}'
		else:
			step_info_description = ''

		# elements_text = self.state.element_tree.clickable_elements_to_string(include_attributes=self.include_attributes)

		# has_content_above = (self.state.pixels_above or 0) > 0
		# has_content_below = (self.state.pixels_below or 0) > 0

		# if elements_text != '':
		# 	if has_content_above:
		# 		elements_text = (
		# 			f'... {self.state.pixels_above} pixels above - scroll or extract content to see more ...\n{elements_text}'
		# 		)
		# 	else:
		# 		elements_text = f'[Start of page]\n{elements_text}'
		# 	if has_content_below:
		# 		elements_text = (
		# 			f'{elements_text}\n... {self.state.pixels_below} pixels below - scroll or extract content to see more ...'
		# 		)
		# 	else:
		# 		elements_text = f'{elements_text}\n[End of page]'
		# else:
		# 	elements_text = 'empty page'

# 		state_description = f"""
# {step_info_description}
# Current url: {self.state.url}
# Available tabs:
# {self.state.tabs}
# Interactive elements from current page view:
# {elements_text}
# """
		state_description = f"""{step_info_description}"""

		if self.result:
			for i, result in enumerate(self.result):
				if result.extracted_content:
					state_description += f'\nAction result {i + 1}/{len(self.result)}: {result.extracted_content}'
				if result.error:
					# only use last 300 characters of error
					error = result.error[-self.max_error_length :]
					state_description += f'\nAction error {i + 1}/{len(self.result)}: ...{error}'

		# if self.state.screenshot:
		# 	# Format message for vision model
		# 	return HumanMessage(
		# 		content=[
		# 			{'type': 'text', 'text': state_description},
		# 			{
		# 				'type': 'image_url',
		# 				'image_url': {'url': f'data:image/png;base64,{self.state.screenshot}'},
		# 			},
		# 		]
		# 	)

		return HumanMessage(content=state_description)


class CustomizedMessageManager(MessageManager):

	def add_state_message(
		self,
		# state: BrowserState,
		result: Optional[List[ActionResult]] = None,
		step_info: Optional[AgentStepInfo] = None,
	) -> None:
		"""Add browser state as human message"""

		# if keep in memory, add to directly to history and add state without result
		if result:
			for r in result:
				if r.include_in_memory:
					if r.extracted_content:
						msg = HumanMessage(content='Action result: ' + str(r.extracted_content))
						self._add_message_with_tokens(msg)
					if r.error:
						msg = HumanMessage(content='Action error: ' + str(r.error)[-self.max_error_length :])
						self._add_message_with_tokens(msg)
					result = None  # if result in history, we dont want to add it again

		# otherwise add state message and result to next message (which will not stay in memory)
		# state_message = AgentMessagePrompt(
		state_message = CustomizedAgentMessagePrompt(
			# state,
			result,
			include_attributes=self.include_attributes,
			max_error_length=self.max_error_length,
			step_info=step_info,
		).get_user_message()
		self._add_message_with_tokens(state_message)


class CustomizedController(Controller):
	def __init__(
		self,
		exclude_actions: list[str] = [],
		output_model: Optional[Type[BaseModel]] = None,
	):
		self.exclude_actions = exclude_actions
		self.output_model = output_model
		self.registry = Registry(exclude_actions)
		# self._register_default_actions()

	def _register_default_actions(self):
		"""Register all default browser actions"""

		if self.output_model is not None:

			@self.registry.action('Complete task', param_model=self.output_model)
			async def done(params: BaseModel):
				return ActionResult(is_done=True, extracted_content=params.model_dump_json())
		else:

			@self.registry.action('Complete task', param_model=DoneAction)
			async def done(params: DoneAction):
				return ActionResult(is_done=True, extracted_content=params.text)


	@time_execution_async('--multi-act')
	async def multi_act(
		self, actions: list[ActionModel], # browser_context: BrowserContext, check_for_new_elements: bool = True
	) -> list[ActionResult]:
		"""Execute multiple actions"""
		results = []

		# session = await browser_context.get_session()
		# cached_selector_map = session.cached_state.selector_map
		# cached_path_hashes = set(e.hash.branch_path_hash for e in cached_selector_map.values())
		# await browser_context.remove_highlights()

		for i, action in enumerate(actions):
			# if action.get_index() is not None and i != 0:
			results.append(await self.act(action))

			logger.debug(f'Executed action {i + 1} / {len(actions)}')
			if results[-1].is_done or results[-1].error or i == len(actions) - 1:
				break

			# await asyncio.sleep(browser_context.config.wait_between_actions)
			# hash all elements. if it is a subset of cached_state its fine - else break (new elements on page)

		return results

	@time_execution_sync('--act')
	async def act(self, action: ActionModel) -> ActionResult:
		"""Execute an action"""
		try:
			for action_name, params in action.model_dump(exclude_unset=True).items():
				if params is not None:
					# remove highlights
					result = await self.registry.execute_action(action_name, params)
					if isinstance(result, str):
						return ActionResult(extracted_content=result)
					elif isinstance(result, ActionResult):
						return result
					elif result is None:
						return ActionResult()
					else:
						raise ValueError(f'Invalid action result type: {type(result)} of {result}')
			return ActionResult()
		except Exception as e:
			raise e




class CustomizedAgent(Agent):
	def __init__(
		self,
		task: str,
		llm: BaseChatModel,
		browser: Browser | None = None,
		browser_context: BrowserContext | None = None,
		controller: CustomizedController = CustomizedController(),
		use_vision: bool = True,
		save_conversation_path: Optional[str] = None,
		save_conversation_path_encoding: Optional[str] = 'utf-8',
		max_failures: int = 3,
		retry_delay: int = 10,
		system_prompt_class: Type[SystemPrompt] = SystemPrompt,
		max_input_tokens: int = 128000,
		validate_output: bool = False,
		message_context: Optional[str] = None,
		generate_gif: bool | str = True,
		include_attributes: list[str] = [
			'title',
			'type',
			'name',
			'role',
			'tabindex',
			'aria-label',
			'placeholder',
			'value',
			'alt',
			'aria-expanded',
		],
		max_error_length: int = 400,
		max_actions_per_step: int = 10,
		tool_call_in_content: bool = True,
		initial_actions: Optional[List[Dict[str, Dict[str, Any]]]] = None,
		# Cloud Callbacks
		register_new_step_callback: Callable[['BrowserState', 'AgentOutput', int], None] | None = None,
		register_done_callback: Callable[['AgentHistoryList'], None] | None = None,
		tool_calling_method: Optional[str] = 'auto',
	):
		self.agent_id = str(uuid.uuid4())  # unique identifier for the agent

		self.task = task
		self.use_vision = use_vision
		self.llm = llm
		self.save_conversation_path = save_conversation_path
		self.save_conversation_path_encoding = save_conversation_path_encoding
		self._last_result = None
		self.include_attributes = include_attributes
		self.max_error_length = max_error_length
		self.generate_gif = generate_gif

		# Controller setup
		self.controller = controller
		self.max_actions_per_step = max_actions_per_step

		# Browser setup
		self.injected_browser = browser is not None
		self.injected_browser_context = browser_context is not None
		self.message_context = message_context

		# Initialize browser first if needed
		self.browser = browser if browser is not None else (None if browser_context else Browser())

		# # Initialize browser context
		# if browser_context:
		# 	self.browser_context = browser_context
		# elif self.browser:
		# 	self.browser_context = BrowserContext(browser=self.browser, config=self.browser.config.new_context_config)
		# else:
		# 	# If neither is provided, create both new
		# 	self.browser = Browser()
		# 	self.browser_context = BrowserContext(browser=self.browser)

		self.system_prompt_class = system_prompt_class

		# Telemetry setup
		self.telemetry = ProductTelemetry()

		# Action and output models setup
		self._setup_action_models()
		self._set_version_and_source()
		self.max_input_tokens = max_input_tokens

		self._set_model_names()

		self.tool_calling_method = self.set_tool_calling_method(tool_calling_method)

		# self.message_manager = MessageManager(
		self.message_manager = CustomizedMessageManager(
			llm=self.llm,
			task=self.task,
			action_descriptions=self.controller.registry.get_prompt_description(),
			system_prompt_class=self.system_prompt_class,
			max_input_tokens=self.max_input_tokens,
			include_attributes=self.include_attributes,
			max_error_length=self.max_error_length,
			max_actions_per_step=self.max_actions_per_step,
			message_context=self.message_context,
		)

		# Step callback
		self.register_new_step_callback = register_new_step_callback
		self.register_done_callback = register_done_callback

		# Tracking variables
		self.history: AgentHistoryList = AgentHistoryList(history=[])
		self.n_steps = 1
		self.consecutive_failures = 0
		self.max_failures = max_failures
		self.retry_delay = retry_delay
		self.validate_output = validate_output
		self.initial_actions = self._convert_initial_actions(initial_actions) if initial_actions else None
		if save_conversation_path:
			logger.info(f'Saving conversation to {save_conversation_path}')

		self._paused = False
		self._stopped = False


	@observe(name='agent.run')
	async def run(self, max_steps: int = 100) -> AgentHistoryList:
		"""Execute the task with maximum number of steps"""
		super().run(max_steps)
		try:
			self._log_agent_run()

			# Execute initial actions if provided
			if self.initial_actions:
				result = await self.controller.multi_act(self.initial_actions, self.browser_context, check_for_new_elements=False)
				self._last_result = result

			for step in range(max_steps):
				if self._too_many_failures():
					break

				# Check control flags before each step
				if not await self._handle_control_flags():
					break

				await self.step()

				if self.history.is_done():
					# NOTE: skip the validation of browser
					# if self.validate_output and step < max_steps - 1:
					# 	if not await self._validate_output():
					# 		continue

					logger.info('✅ Task completed successfully')
					if self.register_done_callback:
						self.register_done_callback(self.history)
					break
			else:
				logger.info('❌ Failed to complete task in maximum steps')

			return self.history
		finally:
			self.telemetry.capture(
				AgentEndTelemetryEvent(
					agent_id=self.agent_id,
					success=self.history.is_done(),
					steps=self.n_steps,
					max_steps_reached=self.n_steps >= max_steps,
					errors=self.history.errors(),
				)
			)

			# if not self.injected_browser_context:
			# 	await self.browser_context.close()

			# if not self.injected_browser and self.browser:
			# 	await self.browser.close()

			# if self.generate_gif:
			# 	output_path: str = 'agent_history.gif'
			# 	if isinstance(self.generate_gif, str):
			# 		output_path = self.generate_gif

			# 	self.create_history_gif(output_path=output_path)


	@time_execution_async('--step')
	async def step(self, step_info: Optional[AgentStepInfo] = None) -> None:
		"""Execute one step of the task"""
		logger.info(f'📍 Step {self.n_steps}')
		state = None
		model_output = None
		result: list[ActionResult] = []

		try:
			# state = await self.browser_context.get_state(use_vision=self.use_vision)

			# if self._stopped or self._paused:
			# 	logger.debug('Agent paused after getting state')
			# 	raise InterruptedError

			# self.message_manager.add_state_message(state, self._last_result, step_info)
			self.message_manager.add_state_message(self._last_result, step_info)
			input_messages = self.message_manager.get_messages()

			try:
				model_output = await self.get_next_action(input_messages)

				if self.register_new_step_callback:
					self.register_new_step_callback(state, model_output, self.n_steps)

				self._save_conversation(input_messages, model_output)
				self.message_manager._remove_last_state_message()  # we dont want the whole state in the chat history

				if self._stopped or self._paused:
					logger.debug('Agent paused after getting next action')
					raise InterruptedError

				self.message_manager.add_model_output(model_output)
			except Exception as e:
				# model call failed, remove last state message from history
				self.message_manager._remove_last_state_message()
				raise e

			result: list[ActionResult] = await self.controller.multi_act(model_output.action)
			for index, r in enumerate(result):
				logger.info(f"  {index}/{len(result)} result: {r}")
			self._last_result = result

			if len(result) > 0 and result[-1].is_done:
				logger.info(f'📄 Result: {result[-1].extracted_content}')

			self.consecutive_failures = 0

		except InterruptedError:
			logger.debug('Agent paused')
			return
		except Exception as e:
			result = await self._handle_step_error(e)
			self._last_result = result


		finally:
			actions = [a.model_dump(exclude_unset=True) for a in model_output.action] if model_output else []
			# self.telemetry.capture(
			# 	AgentStepTelemetryEvent(
			# 		agent_id=self.agent_id,
			# 		step=self.n_steps,
			# 		actions=actions,
			# 		consecutive_failures=self.consecutive_failures,
			# 		step_error=[r.error for r in result if r.error] if result else ['No result'],
			# 	)
			# )
			if not result:
				return

			# if state:
			# NOTE: should to add to history! (so that can stop!!!)
			self._make_history_item(model_output, state, result)


	def _make_history_item(
		self,
		model_output: AgentOutput | None,
		state: BrowserState | None,
		result: list[ActionResult],
	) -> None:
		"""Create and store history item"""
		interacted_element = None
		len_result = len(result)

		# if model_output:
		# 	interacted_elements = AgentHistory.get_interacted_element(model_output, state.selector_map)
		# else:
		# 	interacted_elements = [None]

		# state_history = BrowserStateHistory(
		# 	url=state.url,
		# 	title=state.title,
		# 	tabs=state.tabs,
		# 	interacted_element=interacted_elements,
		# 	screenshot=state.screenshot,
		# )

		history_item = CustomizedAgentHistory(model_output=model_output, result=result)

		self.history.history.append(history_item)

class CustomizedAgentHistory(BaseModel):
	"""History item for agent actions"""
	model_output: AgentOutput | None
	result: list[ActionResult]

	def model_dump(self, **kwargs) -> Dict[str, Any]:
		"""Custom serialization handling circular references"""

		# Handle action serialization
		model_output_dump = None
		if self.model_output:
			action_dump = [
				action.model_dump(exclude_none=True) for action in self.model_output.action
			]
			model_output_dump = {
				'current_state': self.model_output.current_state.model_dump(),
				'action': action_dump,  # This preserves the actual action data
			}

		return {
			'model_output': model_output_dump,
			'result': [r.model_dump(exclude_none=True) for r in self.result],
			# 'state': self.state.to_dict(),
		}
