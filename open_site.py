from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

options = Options()
options.add_experimental_option("detach", True)  # Keep browser open after script ends

driver = webdriver.Chrome(options=options)
driver.get("https://4kirot.com/")

print("Browser opened. Please log in with Gmail manually.")
print("The browser will stay open for you to interact with.")
