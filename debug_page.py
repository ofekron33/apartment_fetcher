"""Quick debug: check what's happening on the page."""

import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


options = Options()
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)
options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
options.add_experimental_option("detach", True)

driver = webdriver.Chrome(options=options)
driver.execute_cdp_cmd("Network.enable", {})

driver.get("https://4kirot.com/")
time.sleep(15)

print(f"Current URL: {driver.current_url}")
print(f"Title: {driver.title}")
print(f"Page body length: {len(driver.page_source)}")

# Check all performance log entries
logs = driver.get_log("performance")
print(f"\nPerformance log entries: {len(logs)}")

methods = {}
for entry in logs:
    msg = json.loads(entry["message"])["message"]
    m = msg["method"]
    methods[m] = methods.get(m, 0) + 1
    if m == "Network.requestWillBeSent":
        url = msg["params"]["request"]["url"]
        if not url.startswith("data:"):
            print(f"  REQ: {url[:120]}")

print(f"\nEvent types: {json.dumps(methods, indent=2)}")

# Check for errors in console
try:
    browser_logs = driver.get_log("browser")
    print(f"\nBrowser console ({len(browser_logs)} entries):")
    for log in browser_logs[:20]:
        print(f"  [{log['level']}] {log['message'][:150]}")
except:
    print("Could not get browser logs")

driver.quit()
