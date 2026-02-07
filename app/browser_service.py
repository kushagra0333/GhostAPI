import asyncio
import time
import traceback
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from app.config import config
from app.models import GenerateRequest, GenerateResponse, TaskStatus, FailureReason
from app.logger import logger
from app.dom_observer import DOMObserver

class BrowserService:
    def __init__(self, request_id: str):
        self.request_id = request_id
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.observer: Optional[DOMObserver] = None
        self.accumulated_text = ""
        self.generation_done = asyncio.Event()
        self.start_time = time.time()

    async def _cleanup(self):
        """Force cleanup of all resources"""
        logger.info("Cleaning up browser resources", extra={"request_id": self.request_id})
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", extra={"request_id": self.request_id})

    async def _on_chunk(self, text: str):
        """Callback for DOMObserver"""
        # We only want to log size, not full text to avoid log spam
        msg_len = len(text)
        prev_len = len(self.accumulated_text)
        if msg_len > prev_len:
            # logger.debug(f"Received chunk update. Length: {msg_len}")
            pass
        self.accumulated_text = text

    async def process_request(self, request: GenerateRequest) -> GenerateResponse:
        logger.info(f"Starting browser processing for request {self.request_id}", extra={"request_id": self.request_id})
        
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                # If you comment this and uncomment this you will be able to see the browser in action
                #headless=False, 
                headless=config.BROWSER_HEADLESS,
                args=["--disable-blink-features=AutomationControlled"]
            )
            
            self.context = await self.browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            
            self.page = await self.context.new_page()
            
            # 1. Navigation
            logger.info("Navigating to ChatGPT", extra={"request_id": self.request_id})
            try:
                await self.page.goto("https://chat.openai.com/", timeout=config.TIMEOUT_PAGE_LOAD * 1000)
            except Exception as e:
                logger.error(f"Navigation timeout or error: {e}", extra={"request_id": self.request_id})
                return self._failure_response(FailureReason.FAIL_TIMEOUT, "Navigation failed")

            # 1.5 Handle potential "Welcome" or "Log in" popups
            logger.info("Waiting for input box", extra={"request_id": self.request_id})
            
            prompt_area = None
            # Expanded selectors list
            selectors = [
                "#prompt-textarea",
                "textarea[id='prompt-textarea']",
                "textarea[data-id='root']",
                "div[contenteditable='true']",
                "textarea[placeholder='Message ChatGPT…']",
                "textarea[placeholder='Message ChatGPT']"
            ]
            
            # Wait a bit for page load
            await asyncio.sleep(2)

            for i in range(10): # retry loop (increased)
                # Check for "Stay logged out"
                try:
                    stay_logged_out = self.page.locator("div", has_text="Stay logged out").last
                    if await stay_logged_out.is_visible():
                        logger.info("Clicking 'Stay logged out'", extra={"request_id": self.request_id})
                        await stay_logged_out.click()
                        await asyncio.sleep(1)
                except:
                    pass

                # Check for "Login" landing page - if we see "Log in" and "Sign up" buttons, we might be stuck
                try:
                    login_btn = self.page.locator("button", has_text="Log in").first
                    if await login_btn.is_visible():
                         logger.warning("Detected 'Log in' button. Might be on landing page.", extra={"request_id": self.request_id})
                         # Potentially could try to click "Start messaging" or similar if available without login, 
                         # but usually "Stay logged out" covers it.
                except:
                    pass

                for selector in selectors:
                    try:
                        loc = self.page.locator(selector).first
                        if await loc.is_visible():
                            prompt_area = loc
                            break
                    except:
                        pass
                
                if prompt_area:
                    break
                
                await asyncio.sleep(1)

            if not prompt_area:
                logger.error("Input box not found. Check if blocked or CAPTCHA.", extra={"request_id": self.request_id})
                await self._take_screenshot("no_input_box")
                await self._dump_html("no_input_box")
                
                # Capture debug info
                page_title = await self.page.title()
                try:
                    body_text = await self.page.inner_text("body")
                    body_snippet = body_text[:500].replace("\n", " ")
                except:
                    body_snippet = "Could not get body text"

                return self._failure_response(FailureReason.FAIL_UI_CHANGE, f"Input box not found. Title: {page_title}. Body: {body_snippet}")

            # 2. Input Prompt
            logger.info(f"Entering prompt into {prompt_area}", extra={"request_id": self.request_id})
            try:
                await prompt_area.fill(request.prompt)
            except:
                # If fill fails (e.g. contenteditable div), try type
                await prompt_area.click()
                await self.page.keyboard.type(request.prompt)
            
            await asyncio.sleep(0.5)

            # Click send button - Try multiple selectors
            send_clicked = False
            send_selectors = [
                "button[data-testid='send-button']", 
                "button[aria-label='Send prompt']",
                "button:has-text('Send')"
            ]
            
            for selector in send_selectors:
                try:
                    btn = self.page.locator(selector).last
                    if await btn.is_visible() and await btn.is_enabled():
                        logger.info(f"Clicking send button: {selector}", extra={"request_id": self.request_id})
                        await btn.click()
                        send_clicked = True
                        break
                except:
                    pass
            
            if not send_clicked:
                logger.info("Send button not found or enabled, pressing Enter", extra={"request_id": self.request_id})
                await self.page.keyboard.press("Enter")

            # 3. Setup Observer
            self.observer = DOMObserver(self.page, self._on_chunk)
            await self.observer.setup()

            # 4. Wait for generation start
            logger.info("Waiting for generation to start", extra={"request_id": self.request_id})
            start_wait = time.time()

            generation_started = False
            
            while time.time() - start_wait < config.TIMEOUT_GENERATION_START:
                # Check for "Sign up to chat" modal or similar blockage
                try:
                    if await self.page.locator("div", has_text="Sign up to chat").is_visible():
                         logger.error("Blocked by 'Sign up to chat' modal", extra={"request_id": self.request_id})
                         await self._take_screenshot("signup_modal")
                         return self._failure_response(FailureReason.FAIL_UI_CHANGE, "Blocked by 'Sign up to chat' modal")
                except:
                    pass

                # Try to find assistant message
                try:
                    # locators = self.page.locator('[data-message-author-role="assistant"]') # old selector
                    # OpenAI often changes classes. .markdown is usually safe but might pick up user message?
                    # User message usually has .whitespace-pre-wrap
                    
                    locators = self.page.locator('.markdown')
                    count = await locators.count()
                    
                    if count > 0:
                        # logger.info(f"Found {count} markdown elements")
                        # We need to make sure it's not the user's prompt (which might be markdown rendered too?)
                        # But honestly, `on_chunk` will handle text updates.
                        # If we attach to the last one, it's likely the new response.
                        
                        last_msg = locators.last
                        # Check if it has content (streaming might start empty)
                        if await last_msg.is_visible():
                             element_handle = await last_msg.element_handle()
                             if element_handle:
                                  await self.observer.attach(element_handle)
                except Exception as e:
                    pass

                if self.accumulated_text:
                    generation_started = True
                    break
                
                if await self.observer.check_generation_indicators():
                    generation_started = True
                    break
                    
                await asyncio.sleep(0.5)

            if not generation_started:
                 logger.error("Generation did not start", extra={"request_id": self.request_id})
                 await self._take_screenshot("generation_not_started")
                 await self._dump_html("generation_not_started")
                 return self._failure_response(FailureReason.FAIL_TIMEOUT, "Generation did not start")

            logger.info("Generation started. Streaming...", extra={"request_id": self.request_id})

            # 5. Monitor for completion
            last_change_time = time.time()
            last_text_len = 0
            
            while True:
                if time.time() - self.start_time > config.TIMEOUT_GLOBAL_HARD_LIMIT:
                     return self._failure_response(FailureReason.FAIL_TIMEOUT, "Global hard limit reached")
                
                current_len = len(self.accumulated_text)
                now = time.time()
                
                if current_len != last_text_len:
                    last_change_time = now
                    last_text_len = current_len
                
                if now - last_change_time > config.TIMEOUT_GENERATION_INACTIVITY:
                    is_stop_visible = await self.observer.check_generation_indicators()
                    if not is_stop_visible:
                        logger.info("Generation detected complete (inactivity + no stop button)", extra={"request_id": self.request_id})
                        break
                
                await asyncio.sleep(0.5)

            return GenerateResponse(
                request_id=self.request_id,
                status=TaskStatus.COMPLETED,
                output_text=self.accumulated_text,
                failure_reason=FailureReason.SUCCESS_FULL,
                latency_ms=int((time.time() - self.start_time) * 1000)
            )

        except Exception as e:
            logger.error(f"Unexpected error: {e}\n{traceback.format_exc()}", extra={"request_id": self.request_id})
            await self._take_screenshot("unexpected_error")
            await self._dump_html("unexpected_error")
            return self._failure_response(FailureReason.FAIL_UNKNOWN, str(e))
            
        finally:
            await self._cleanup()

    async def _take_screenshot(self, name: str):
        if self.page:
            try:
                path = f"{config.SCREENSHOT_DIR}/{self.request_id}_{name}.png"
                await self.page.screenshot(path=path)
                logger.info(f"Screenshot saved to {path}", extra={"request_id": self.request_id})
            except Exception as e:
                logger.error(f"Failed to take screenshot: {e}", extra={"request_id": self.request_id})

    async def _dump_html(self, name: str):
        if self.page:
            try:
                path = f"{config.HTML_SNAPSHOT_DIR}/{self.request_id}_{name}.html"
                content = await self.page.content()
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info(f"HTML snapshot saved to {path}", extra={"request_id": self.request_id})
            except Exception as e:
                logger.error(f"Failed to save HTML snapshot: {e}", extra={"request_id": self.request_id})

    def _failure_response(self, reason: FailureReason, msg: str) -> GenerateResponse:
        return GenerateResponse(
            request_id=self.request_id,
            status=TaskStatus.FAILED,
            failure_reason=reason,
            output_text=self.accumulated_text, # Return partial text if any
            error_message=msg,
            latency_ms=int((time.time() - self.start_time) * 1000)
        )
