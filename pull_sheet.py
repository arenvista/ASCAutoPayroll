import os
import pandas as pd
from time import sleep
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.keys import Keys # Added Keys import
from selenium.common.exceptions import TimeoutException

import os
from dotenv import load_dotenv

def login_umbc(driver, web_addr):
    load_dotenv(dotenv_path=os.path.join(os.getcwd(), 'pass.env'))

    username = os.getenv('UMBC_USR')
    password = os.getenv('UMBC_PAS')
    print(f" Username => {username}\n Passowrd => {password} ")

    print("Setting up Firefox profile in CWD...")
    options = Options()
    profile_path = os.path.join(os.getcwd(), "firefox_profile")
    options.add_argument("-profile")
    options.add_argument(profile_path)

    print(f"Using profile at: {profile_path}")
    print("Getting Driver...")
    driver.get(web_addr)

    wait = WebDriverWait(driver, 15) # Increased slightly for PeopleSoft load times

    field_uname = '//*[@id="username"]'
    field_pass = '//*[@id="password"]'

    if username is None: exit()
    if password is None: exit()

    date_input = wait.until(EC.element_to_be_clickable((By.XPATH, field_uname)))
    date_input.send_keys(username)
    date_input = wait.until(EC.element_to_be_clickable((By.XPATH, field_pass)))
    date_input.send_keys(password)
    driver.find_element(By.XPATH, '//*[@id="submitButton"]').click()  # Clicks the button with id 'submitButton'
    sleep(10)

print("Setting up Firefox profile in CWD...")
options = Options()
profile_path = os.path.join(os.getcwd(), "firefox_profile")
options.add_argument("-profile")
options.add_argument(profile_path)

print(f"Using profile at: {profile_path}")
print("Getting Driver...")

driver = webdriver.Firefox(options=options)

timesheet_page = "https://traccloud.go-redrock.com/umbc/trac/listing.php?navSrch=all&form=list&tbl=Visits&rsrc=&searchForm=true&previousSearch=Previous+Search%3A+month&previousSearch_Visits=Previous+Search%3A+month&isPrint=true"
login_umbc(driver,timesheet_page)

sleep(10)

# Get the current page's HTML source
html_source = driver.page_source

# Save to a file
import os
filepath = os.path.join(os.environ['HOME'], 'Downloads/old/parse/Attendance Listing.html')
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(html_source)

driver.quit()
