import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path

from browser_use.agent.views import ActionResult

import asyncio

from langchain_openai import ChatOpenAI

from browser_use import Agent, Controller, SystemPrompt
from browser_use.browser.browser import Browser, BrowserConfig
from browser_use.browser.context import BrowserContext, BrowserContextConfig

import os
api_key = os.getenv('LITELLM_API_KEY')
base_url = os.getenv('LITELLM_BASE_URL')

llm = ChatOpenAI(model='gpt-4o', api_key=api_key, base_url=base_url)
# llm = ChatOpenAI(model='gpt-4o')

extend_system_messages = """
- 对于 https://meeting.woa.com/book:
	- 若需要预约某一会议室, 请依次点击 "时间段" 部分的白色区域两次, 来选择开始和结束时间. (在弹出的页面中, 请确认时间段正确)
""".strip()


# Initialize controller first
browser = Browser(
	config=BrowserConfig(
		headless=False,
		chrome_instance_path='/Applications/Chromium.app/Contents/MacOS/Chromium',
		# chrome_instance_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
	),
)
config = BrowserContextConfig(
	# cookies_file="path/to/cookies.json",
	# wait_for_network_idle_page_load_time=3.0,
	# browser_window_size={'width': 1280, 'height': 1100},
	# locale='en-US',
	# user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36',
	# highlight_elements=False,
	# viewport_expansion=500,
	# allowed_domains=['google.com', 'wikipedia.org'],
	extend_system_messages=extend_system_messages,
)
context = BrowserContext(browser=browser, config=config)

async def main():
	# task="帮我在 https://meeting.woa.com/ 网站订一个会议室，地点是成都腾讯大厦A座9楼，时间是今天下午19:00-20:00",
	# task="帮我在 https://meeting.woa.com/ 网站订一个会议室，地点是上海腾讯滨江大厦15楼，时间是今天下午19:00-20:00",
	task = input("Please enter your task: ").strip()
	agent = Agent(
		task=task,
		llm=llm,
		browser=browser,
		browser_context=context,
		# use_vision=False,
	)
	result = await agent.run()
	print(result)

asyncio.run(main())