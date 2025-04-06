""" 
NOTE: 适用于 0.1.40, 新版取消了 SystemPrompt 接口, 暂时无法跑通
"""

from agent_no import CustomizedController, CustomizedAgent, ActionResult
from langchain_openai import ChatOpenAI
import logging, json
import asyncio
from browser_use.controller.views import DoneAction
from browser_use import Agent, Controller, SystemPrompt

import os
api_key = os.getenv('LITELLM_API_KEY')
base_url = os.getenv('LITELLM_BASE_URL')

llm = ChatOpenAI(model='gpt-4o', api_key=api_key, base_url=base_url)
llm_small = ChatOpenAI(model='TIONE_qwen25-72B-INT8_eason', api_key=api_key, base_url=base_url)

logger = logging.getLogger(__name__)

class MySystemPrompt(SystemPrompt):
	def important_rules(self) -> str:
		existing_rules = super().important_rules()
		new_rules = """
- 多任务并发处理: 对于多文件的处理, 你一次可以生成多个动作!!!
- 工作路径: 请在用户所给文件的目录下进行文件操作
- 任务输出: 请将你最终的解答写入到 result.md 文件中, 中文, Markdown 格式, 表达清晰, 可以借助表格等形式进行输出
""".strip()
		return f'{existing_rules}\n{new_rules}'


import fitz  # PyMuPDF
def extract_text_with_pymupdf(file_path):
	document = fitz.open(file_path)
	text = ""
	for page in document:
		text += page.get_text()
	return text

controller = CustomizedController()

# @controller.action('Read the file content of a file given a path')
async def read_file(path: str):
	if path.endswith('.pdf'):
		content = extract_text_with_pymupdf(path)
	else:
		with open(path, 'r') as f:
			content = f.read()
	msg = f'File content: {content}'
	# logger.info(msg)
	return ActionResult(extracted_content=msg, include_in_memory=True)

@controller.action('Write content to a file given a path and content')
async def write_file(path: str, content: str):
	with open(path, 'w') as f:
		f.write(content)
	return ActionResult(extracted_content=f'Content written to {path}', include_in_memory=True)

@controller.action('Extract information from a file given a path and your interested informations, the output is a JSON object (support PDF and TXT format)')
async def file_content_extractor(path: str, question: str):
    content = await read_file(path)
    query = f"Given the content of a file, please answer the following question in structured format (like JSON): {question}. \n\n{content.extracted_content}"
    result = await llm_small.ainvoke(query)
    return ActionResult(extracted_content=result.content, include_in_memory=True)

@controller.action('Complete task', param_model=DoneAction)
async def done(params: DoneAction):
	# with open('result.md', 'w') as f:
	# 	f.write(params.text)
	return ActionResult(is_done=True, extracted_content=params.text)

@controller.action("Shell command execution")
async def shell_command(exec_dir: str, command: str):
    import subprocess, os
    if not os.path.exists(exec_dir):
        return ActionResult(error=f"Directory {exec_dir} does not exist")
    try:
        result = subprocess.run([command], shell=True, cwd=exec_dir, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return ActionResult(extracted_content=result.stdout.decode('utf-8'), include_in_memory=True)
    except subprocess.CalledProcessError as e:
        return ActionResult(error=f"Command failed with error: {e.stderr.decode('utf-8')}")

from camel.interpreters import InternalPythonInterpreter
python_interpreter = InternalPythonInterpreter(unsafe_mode=True)
@controller.action("Python executor. Use `print` to output result. (only use it for data analysis!)")
async def python_executor(code: str):
    output = python_interpreter.run(code, "python")
    return ActionResult(extracted_content=f"> Execution result: {output}", include_in_memory=True)


async def main():
	# task="我电脑上有很多简历 (/Users/frankshi/Downloads/_tmp/resumes.7z)，请分析这些简历并对它们按以下规则加权计算进行排序，20%学历、50%经历、20%奖项、10%爱好",
	task = input("Please enter your task: ").strip()
	agent = CustomizedAgent(
		task=task,
		llm=llm,
		controller=controller,
		system_prompt_class=MySystemPrompt,
	)
	result = await agent.run()
	with open("session.log", "w") as f:
		f.write(json.dumps(result.model_dump(), ensure_ascii=False))
	# print(result)


if __name__ == '__main__':
	asyncio.run(main())
