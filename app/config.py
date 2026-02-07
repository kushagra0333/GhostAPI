import os

class Config:
    # Service Configuration
    HOST = "127.0.0.1"
    PORT = 8000
    
    # Browser Automation Configuration
    MAX_CONCURRENT_BROWSERS = 2
    BROWSER_HEADLESS = True  # Set to True for production/background running
    
    # Timeouts (in seconds)
    TIMEOUT_GLOBAL_HARD_LIMIT = 300  # 5 minutes
    TIMEOUT_PAGE_LOAD = 30
    TIMEOUT_GENERATION_START = 60
    TIMEOUT_GENERATION_INACTIVITY = 4
    
    # Paths
    SCREENSHOT_DIR = "logs/screenshots"
    HTML_SNAPSHOT_DIR = "logs/html"
    
    # Ensure log directories exist
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    os.makedirs(HTML_SNAPSHOT_DIR, exist_ok=True)

config = Config()
