import asyncio
import base64
import json
import pathlib
import urllib.parse
from datetime import datetime
from dataclasses import dataclass, asdict
from browser_use import Browser, BrowserConfig
from browser_use.browser.browser import BrowserContext
from browser_use.dom.service import DomService
from browser_use.browser.views import BrowserState
from playwright.async_api import Page


async def remove_highlights(page: Page):
    await page.evaluate(
        """
        try {
            // Remove the highlight container and all its contents
            const container = document.getElementById('playwright-highlight-container');
            if (container) {
                container.remove();
            }

            // Remove highlight attributes from elements
            const highlightedElements = document.querySelectorAll('[browser-user-highlight-id^="playwright-highlight-"]');
            highlightedElements.forEach(el => {
                el.removeAttribute('browser-user-highlight-id');
            });
        } catch (e) {
            console.error('Failed to remove highlights:', e);
        }
        """
    )

async def get_highlighted_elements(page: Page):
    await remove_highlights(page)

    dom_service = DomService(page)
    content = await dom_service.get_clickable_elements(
        focus_element=-1,
        viewport_expansion=500,
        highlight_elements=True,
    )
    return content

async def take_screenshot(browser_context: BrowserContext, output_path: pathlib.Path):
    screenshot_b64 = await browser_context.take_screenshot(full_page=False)
    file = base64.b64decode(screenshot_b64)
    with open(output_path, 'wb') as f: f.write(file)

async def save_state(browser_context: BrowserContext, page: Page, output_path: pathlib.Path):
    output_path.mkdir(parents=True, exist_ok=True)
    await take_screenshot(browser_context, output_path / 'screenshot_original.png')
    state = await browser_context.get_state()
    with open(output_path / 'state.json', 'w') as f: f.write(str(state))
    user_message = get_user_message(state)
    with open(output_path / 'user_message.txt', 'w') as f: f.write(user_message)
    interactive_message = get_interactive_message(state)
    with open(output_path / 'screenshot_original.rec', 'w') as f: f.write(interactive_message)
    await get_highlighted_elements(page)
    await take_screenshot(browser_context, output_path / 'screenshot_highlight.png')


async def task(url: str, output_path: pathlib.Path):
    browser = Browser(
        config=BrowserConfig(
            headless=False, # True,
            chrome_instance_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        )
    )  # True
    async with BrowserContext(browser=browser) as browser_context:
        page = await browser_context.get_current_page()

        await page.goto(url)
        await save_state(browser_context, page, output_path / '01')

        await page.evaluate('window.scrollBy(0, window.innerHeight);')
        await save_state(browser_context, page, output_path / '02')

    await browser.close()

include_attributes = [
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
    'rect',
]

def get_user_message(state: BrowserState) -> str:
    elements_text = state.element_tree.clickable_elements_to_string(include_attributes=include_attributes)

    has_content_above = (state.pixels_above or 0) > 0
    has_content_below = (state.pixels_below or 0) > 0

    if elements_text != '':
        if has_content_above:
            elements_text = (
                f'... {state.pixels_above} pixels above - scroll or extract content to see more ...\n{elements_text}'
            )
        else:
            elements_text = f'[Start of page]\n{elements_text}'
        if has_content_below:
            elements_text = (
                f'{elements_text}\n... {state.pixels_below} pixels below - scroll or extract content to see more ...'
            )
        else:
            elements_text = f'{elements_text}\n[End of page]'
    else:
        elements_text = 'empty page'

    # if step_info:
    #     step_info_description = f'Current step: {step_info.step_number + 1}/{step_info.max_steps}'
    # else:
    #     step_info_description = ''
    step_info_description = ''
    time_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    step_info_description += f'Current date and time: {time_str}'

    state_description = f"""
[Task history memory ends]
[Current state starts here]
The following is one-time information - if you need to remember it write it to memory:
Current url: {state.url}
Available tabs:
{state.tabs}
Interactive elements from top layer of the current page inside the viewport:
{elements_text}
{step_info_description}
"""

    return state_description


def get_interactive_message(state: BrowserState) -> str:
    elements_text = state.element_tree.clickable_elements_to_rect(include_attributes=include_attributes)
    return elements_text

if __name__ == '__main__':
    odir = pathlib.Path(__file__).parent / 'states'
    odir.mkdir(parents=True, exist_ok=True)
    for url in [
        "https://www.baidu.com/",
        # "https://www.mydown.com/",
        # "https://weixin.qq.com/",
        # "https://guanjia.qq.com/",
        # "https://browser.qq.com/mac",
        # "https://shurufa.sogou.com/mac",
        # "https://xmsoushu.com/#/",
        # "https://im.qq.com/index/",
        # # "https://browser.qq.com/mac",
        # "https://www.onlinedown.net/",
        # "https://www.iyd.wang/",
        # "https://store.steampowered.com/",
        # "http://www.shuyy8.cc/",
        # "https://www.qishu99.cc/",
        # "https://xiazai.zol.com.cn/",
        # "http://www.downcc.com/",
        # "https://xiazai.zol.com.cn/",
        # "https://baoku.360.cn/",
        # "http://www.banshujiang.cn/",
    ]:
        print(f"Processing {url}")
        domain = urllib.parse.urlparse(url).netloc
        output_dir = odir / domain
        output_dir.mkdir(parents=True, exist_ok=True)
        asyncio.run(task(url, output_dir))


