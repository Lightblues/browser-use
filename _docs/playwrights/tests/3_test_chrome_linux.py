
from dotenv import load_dotenv
import os
import sys
import logging
from typing import Dict, Any

from playwright.sync_api import sync_playwright
from playwright.async_api import Browser as PlaywrightBrowser
from playwright.sync_api import Page, expect
from playwright.async_api import (
	Playwright,
	async_playwright,
)

load_dotenv()

import asyncio

cdp_url = "http://9.134.230.111:9222"
# cdp_url = 'http://127.0.0.1:9333'
# curl http://9.134.230.111:9222/json/version

logger = logging.getLogger(__name__)

async def setup_cdp(playwright: Playwright) -> PlaywrightBrowser:
    """Sets up and returns a Playwright Browser instance with anti-detection measures."""
    if not cdp_url:
        raise ValueError('CDP URL is required')
    logger.info(f'Connecting to remote browser via CDP {cdp_url}')
    browser = await playwright.chromium.connect_over_cdp(cdp_url)
    return browser

async def test_baidu(semaphore, playwright: Playwright):
    async with semaphore:
        try:
            browser = await setup_cdp(playwright)
            # new tab
            #currentContext = browser.contexts[0]
            # new process
            currentContext = await browser.new_context()
            currentContext.set_default_timeout(100000) 
            page = await currentContext.new_page()
            print("open Baidu.")
            await page.goto("https://www.baidu.com/")
            print("open Baidu:1")
            await page.locator("#kw").click()
            await page.wait_for_load_state('load')

            contentList = [
            "selenium",
            "deepseek",
            "v.qq.com",
            ] 

            for content in contentList:
                await page.locator("#kw").fill(content)
                await page.get_by_role("button", name="百度一下").click()
                #await asyncio.sleep(1)
                await page.locator("#kw").click()
                await page.locator("#kw").clear()
                await page.wait_for_load_state()

            value = await page.locator("#kw").input_value()
            #assert value == "selenium", f"Expected 'selenium', but got '{value}'"
            await page.wait_for_load_state()
            #if (value == "selenium"):
            await page.screenshot(path='baidu_screenshot.png')
            await asyncio.sleep(2)
            print("Screenshot taken for Baidu.")
            await currentContext.close()
            await browser.close()
        except Exception as e:
            print(f'Failed to cleanup browser in destructor: {e}')
        print("close Baidu.")
            

async def testLoopRun(playwright):
    #async with async_playwright() as playwright:
    semaphore = asyncio.Semaphore(200)  # Limit to 5 concurrent tasks
    to_testaa = [asyncio.create_task(test_baidu(semaphore, playwright)) for _ in range(20)]
    # Wait for the first task to complete
    #done, pending =  await asyncio.gather(*to_testaa)
    done, pending = await asyncio.wait(to_testaa, return_when=asyncio.ALL_COMPLETED)
    print(f"Completed {len(done)} tasks.")
    # Optionally, you can handle pending tasks if needed
    for task in pending:
        print("Pending task:", task)

async def run():
    playwright = await async_playwright().start()
    await testLoopRun(playwright)
    await playwright.stop()
   
async def main():
    print("main:begin:")
    await run()
    print("main:end:")

asyncio.run(main())