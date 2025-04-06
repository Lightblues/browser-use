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

import logging
logger = logging.getLogger(__name__)

llm = ChatOpenAI(model='gpt-4o', api_key=api_key, base_url=base_url)


import fitz  # PyMuPDF
def extract_text_with_pymupdf(file_path):
	document = fitz.open(file_path)
	text = ""
	for page in document:
		text += page.get_text()
	return text


controller = Controller()

@controller.action('Read the file content of a file given a path')
async def read_file(path: str):
	if path.endswith('.pdf'):
		content = extract_text_with_pymupdf(path)
	else:
		with open(path, 'r') as f:
			content = f.read()
	msg = f'File content: {content}'
	logger.info(msg)
	return ActionResult(extracted_content=msg, include_in_memory=True)




# Initialize controller first
browser = Browser(
	config=BrowserConfig(
		headless=False,
		# chrome_instance_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
		chrome_instance_path='/Applications/Chromium.app/Contents/MacOS/Chromium',
	),
)
config = BrowserContextConfig(
	# cookies_file="path/to/cookies.json",
	# wait_for_network_idle_page_load_time=3.0,
	# browser_window_size={'width': 1280, 'height': 1100},
	# locale='en-US',
	# user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36',
	highlight_elements=True,
	# viewport_expansion=500,
	# allowed_domains=['google.com', 'wikipedia.org'],
)
context = BrowserContext(browser=browser, config=config)

async def main():
	# task="我电脑上有一份简历'/Users/frankshi/Downloads/resumes/li xiaohua.pdf'，请解析它并在智联招聘网站上寻找合适的岗位投递",
	# task="我电脑上有一份简历'/Users/frankshi/Downloads/resumes/li xiaohua.pdf'，请解析它并在智联招聘网站上寻找匹配的3个岗位",
	# task="我电脑上有一份简历'/Users/frankshi/Downloads/resumes/li xiaohua.pdf'，请解析它并在智联招聘网站上寻找匹配的3个岗位, 并完成投递",
	# task = input("Please enter your task: ").strip()
	task = """帮我总结下面三个网页: 
https://quote.eastmoney.com/hk/02097.html
https://finance.sina.com.cn/stock/stockzmt/2025-03-03/doc-inenkfen0796630.shtml
https://xueqiu.com/S/02097"""

	agent = Agent(
		task=task,
		llm=llm,
		controller=controller,
		# available_file_paths=["/Users/frankshi/Downloads/visiky_s resume.pdf"],
		browser=browser,
		browser_context=context,
		# use_vision=False,
	)
	result = await agent.run()
	# print(result)

asyncio.run(main())