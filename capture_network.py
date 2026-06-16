import asyncio
import json
import os
from playwright.async_api import async_playwright

async def capture():
    # Find cookies file
    cookies_path = "semparar_api/semparar_cookies.json"
    if not os.path.exists(cookies_path):
        cookies_path = "semparar_cookies.json"
        
    if not os.path.exists(cookies_path):
        print(f"Error: {cookies_path} not found.")
        return
        
    with open(cookies_path, "r") as f:
        raw_cookies = json.load(f)
        
    print(f"Loaded {len(raw_cookies)} cookies.")
    
    # Format cookies for Playwright
    playwright_cookies = []
    for c in raw_cookies:
        # Playwright requires specific names and types
        pw_cookie = {
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c.get("path", "/"),
            "secure": c.get("secure", True),
            "httpOnly": c.get("httpOnly", False),
        }
        # sameSite must be one of 'Lax', 'None', 'Strict'
        ss = c.get("sameSite")
        if ss:
            if "no_restriction" in ss.lower():
                pw_cookie["sameSite"] = "None"
            elif "lax" in ss.lower():
                pw_cookie["sameSite"] = "Lax"
            elif "strict" in ss.lower():
                pw_cookie["sameSite"] = "Strict"
        playwright_cookies.append(pw_cookie)

    async with async_playwright() as p:
        # Launch headless chromium
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        
        # Load cookies
        await context.add_cookies(playwright_cookies)
        
        page = await context.new_page()
        
        # Intercept and log requests
        def handle_request(request):
            if "dados-cadastrais" in request.url or "api" in request.url or "fatura" in request.url or "financeiro" in request.url or "json" in request.url:
                print(f"[Request] {request.method} -> {request.url}")
                
        async def handle_response(response):
            url = response.url
            if "api" in url or "dados" in url or "fatura" in url or "financeiro" in url or "json" in url:
                print(f"[Response] {response.status} <- {url}")
                try:
                    # Try to print response body if JSON or text
                    content_type = response.headers.get("content-type", "")
                    if "json" in content_type.lower():
                        body = await response.json()
                        print(f"  Body (JSON): {json.dumps(body, indent=2)[:1000]}")
                    elif "text" in content_type.lower() and len(url) < 150:
                        text = await response.text()
                        print(f"  Body (Text): {text[:500]}")
                except Exception as e:
                    print(f"  Could not read body: {e}")

        page.on("request", handle_request)
        page.on("response", handle_response)
        
        print("Navigating to dados-cadastrais...")
        await page.goto("https://portal.sempararempresas.com.br/tag/empresa/dados-cadastrais")
        
        # Wait 10 seconds for XHR and page load to complete
        await asyncio.sleep(10)
        
        print("\nPage title:", await page.title())
        
        # Now let us try navigating to the seguro URL to see if it redirects or authenticates
        print("\nNavigating to faturas...")
        await page.goto("https://seguro.sempararempresas.com.br/Financeiro/Fatura/ConsultarFaturas_AbaProdutoListarTipo?codigoTipoProduto=STP")
        
        await asyncio.sleep(5)
        print("Final URL after seguro navigation:", page.url)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(capture())
