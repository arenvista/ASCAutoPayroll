import asyncio
import questionary
from time import sleep
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class UMBCTimesheetScraper:
    def __init__(self, driver, config) -> None:
        self.driver = driver
        self.config = config
        self.target_url: str = "https://traccloud.go-redrock.com/umbc/trac/listing.php?navSrch=all&form=list&tbl=Visits&rsrc=&searchForm=true&previousSearch=Previous+Search%3A+month&previousSearch_Visits=Previous+Search%3A+month&isPrint=true"
        self.output_file: Path = self.config.html_file
        
        self.username = self.config.umbc_usr
        self.password = self.config.umbc_pass
        
        if not self.username or not self.password:
            raise ValueError("Missing UMBC credentials in config.")

    async def login(self) -> None:
        print("Navigating to target URL...")
        self.driver.get(self.target_url)
        wait = WebDriverWait(self.driver, 15)

        username_field = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="username"]')))
        username_field.send_keys(self.username)

        password_field = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="password"]')))
        password_field.send_keys(self.password)

        submit_button = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="submitButton"]')))
        submit_button.click()

        wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body"))).send_keys("\ue00c")

    async def fetch_and_save_html(self) -> None:
        choice = await questionary.select(
            "Finished Loading Page?",
            choices=["Yes"],
            use_indicator=True,
        ).ask_async()

        html_source: str = self.driver.page_source
        self.config.data_dir.mkdir(parents=True, exist_ok=True)

        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.write(html_source)

        print(f"Save successful to {self.output_file}!")

    async def run(self) -> None:
        await self.login()
        # Ensure you await the async fetching method
        await self.fetch_and_save_html()
