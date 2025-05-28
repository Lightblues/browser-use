import pathlib
from playwright.async_api import async_playwright, Download as AsyncDownload
from playwright.sync_api import sync_playwright, Download
import asyncio
import aiohttp

url = "https://static.www.tencent.com/uploads/2025/03/19/5894f24eb4ade2dea94826d62bd7b11b.pdf"
# default: download to user's home directory / FA_BU
downlod_prefix = pathlib.Path.home() / "Downloads" / "FA_BU"
downlod_prefix.mkdir(parents=True, exist_ok=True)

# with sync_playwright() as p:
#     browser = p.chromium.launch(headless=False)
#     context = browser.new_context(accept_downloads=True)
#     # 设置自定义请求头，强制触发下载
#     headers = {
#         "Accept": "application/octet-stream"  # 告诉服务器直接返回文件
#     }
#     context.set_extra_http_headers(headers)
#     page = context.new_page()
#     page.goto(url)
#     with page.expect_download() as download_info:
#         pass  # 等待下载
#     download = download_info.value
#     print(f"下载路径: {download.path()}")
#     download.save_as("/path/to/save/example.pdf")
#     context.close()
#     browser.close()

async def download_async():
    async with async_playwright() as p:
        # 创建一个特定的下载目录
        browser = await p.chromium.launch(
            headless=False,
            executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        )
        context = await browser.new_context(
            accept_downloads=True,
        )
        # 监听整个上下文中的下载事件
        downloads: list[AsyncDownload] = []
        async def on_download(download: AsyncDownload):
            print(f"Download: {download.suggested_filename}, URL: {download.url}")
            # print(f"Download path: {await download.path()}")
            downloads.append(download)
        
        page = await context.new_page()
        page.on("download", on_download)

        # 执行会触发下载的操作
        await page.goto("https://www.jjjxsw.com/txt/dl-16-35026.html")
        await page.get_by_text("TXT电子书下载地址【无需解压缩】").click()

        await page.goto("https://sci-hub.se/10.1016/j.enconman.2017.07.047")
        await page.get_by_text("save").click()
        
        await page.goto("https://www.onlinedown.net/soft/759217.htm")
        await page.get_by_text("本地网络下载").click()

        # 查看所有下载
        for i, download in enumerate(downloads):
            print(f"> {i+1}: {download.suggested_filename}, URL: {download.url}")
            ofn = f"{downlod_prefix}/{download.suggested_filename}"
            await download.save_as(ofn)
            print(f"  Downloaded to {ofn}")
            
            # 可以保存到指定位置
            # download.save_as(f"./my_downloads/{download.suggested_filename}")
        
        await browser.close()

def download_sync():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        )
        context = browser.new_context(
            accept_downloads=True,
        )

        page = context.new_page()
        def on_download(download: Download):
            print(f"Download path: {download.path()}")
        page.on("download", on_download)
        
        # 执行会触发下载的操作
        response = page.goto("https://www.jjjxsw.com/txt/dl-16-35026.html")
        response = page.click("text=TXT电子书下载地址【无需解压缩】")
        response = page.goto("https://sci-hub.se/10.1016/j.enconman.2017.07.047")
        response = page.click("text=save")
        response = page.goto("https://www.onlinedown.net/soft/759217.htm")
        response = page.click("text=本地网络下载")
        
        context.close()
        browser.close()

async def download_direct_pdf(url: str, filename: str = None) -> str:
    """Download a file directly from the URL.
    
    Args:
        url (str): The URL of the file to download.
        filename (str, optional): The name of the file to save. If not provided, the filename will be extracted from the URL.
    """
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    if not filename:
                        filename = url.split("/")[-1]
                    file_path = downlod_prefix / filename
                    with open(file_path, "wb") as f:
                        while True:
                            chunk = await response.content.readany()
                            if not chunk:
                                break
                            f.write(chunk)
                    return f"Successfully downloaded into {file_path}"
                else:
                    return f"Failed to download, status code: {response.status}"
        except Exception as e:
            return f"Failed to download: {str(e)}"



if __name__ == '__main__':
    # asyncio.run(download_direct_pdf(url, ofn))
    asyncio.run(download_async())
    # download_sync()