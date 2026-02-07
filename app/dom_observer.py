import asyncio
from typing import Callable
from playwright.async_api import Page
from app.logger import logger

class DOMObserver:
    def __init__(self, page: Page, on_chunk: Callable[[str], None]):
        self.page = page
        self.on_chunk = on_chunk

    async def setup(self):
        """
        Expose the python function to the browser context.
        """
        await self.page.expose_function("on_mutation_py", self._handle_mutation)

    async def _handle_mutation(self, text: str):
        # logger.info(f"DOMObserver: received mutation text: {text}")
        if text is not None:
             # logger.info(f"DOMObserver: calling on_chunk with {len(text)} chars")
             if asyncio.iscoroutinefunction(self.on_chunk):
                 await self.on_chunk(text)
             else:
                 self.on_chunk(text)

    async def attach(self, element_handle):
        """
        Attaches the mutation observer to the specific element handle.
        """
        script = """
        (element) => {
            console.log("DOMObserver: attach() called");
            
            if (window._observerInstalled) {
                console.log("DOMObserver: already installed");
                return;
            }

            if (!element) {
                console.log("DOMObserver: Element is null");
                return;
            }

            console.log("DOMObserver: Target found (via handle), installing observer");
            window._observerInstalled = true;
            
            // Send initial text
            console.log("DOMObserver: Sending initial text length: " + element.innerText.length);
            window.on_mutation_py(element.innerText);

            const observer = new MutationObserver((mutations) => {
                console.log("DOMObserver: Mutation detected");
                window.on_mutation_py(element.innerText);
            });

            observer.observe(element, {
                childList: true, 
                subtree: true, 
                characterData: true
            });
        }
        """
        await self.page.evaluate(script, element_handle)

    async def check_generation_indicators(self) -> bool:
        # Check for stop button
        # Using a broad selector for robustness
        stop_btn = self.page.locator("button[aria-label='Stop generating']")
        return await stop_btn.is_visible()

