import pandas as pd
from time import sleep
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
import questionary

class TimesheetAutomator:
    """Automates UMBC timesheet entry using Selenium and Pandas."""

    def __init__(self, driver, wait, config) -> None:
        self.config = config
        self.driver = driver
        self.wait = wait
        self._validate_setup()

    def _validate_setup(self) -> None:
        if self.driver is None or self.wait is None:
            raise ValueError("Driver / Wait did not start properly from interface.")

    def login_umbc(self, login_url: str) -> None:
        """Automates the initial login process."""
        username = self.config.umbc_usr
        password = self.config.umbc_pass
        
        if not username or not password:
            print("Error: Missing credentials in configuration.")
            return

        print(f"[NAVIGATING TO TIMESHEET PAGE] => {login_url}")
        print(f"\tUsername => {username}\n\tPassword => {'*' * len(password)}")
        self.driver.get(login_url)

        try:
            uname_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="username"]')))
            uname_input.send_keys(username)
            
            pass_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="password"]')))
            pass_input.send_keys(password)
            
            self.driver.find_element(By.XPATH, '//*[@id="submitButton"]').click()
            # sleep(10) # Allow time for redirection
        except TimeoutException:
            print("Login fields not found in time.")

    def _switch_to_peoplesoft_iframe(self) -> bool:
        """Locates and switches to the correct PeopleSoft iframe."""
        try:
            print("Switching to PeopleSoft iframe...")
            self.wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "ptModFrame_0")))
            print("Successfully switched to modal iframe (ptModFrame_0).")
            return True
        except TimeoutException:
            print("Modal iframe not found. Trying main content iframe...")
            try:
                self.wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "ptifrmtgtframe")))
                print("Successfully switched to main iframe (ptifrmtgtframe).")
                return True
            except TimeoutException:
                print("Could not find either iframe. The script will likely fail.")
                return False

    def _enter_row_data(self, index: int, row: pd.Series, is_last_row: bool, timer: float = 0.5) -> None:
        """Inputs a single row of data from the DataFrame into the timesheet."""
        print(f"--- Row Index: {index} ---")
        
        xpaths = {
            'date': f"//*[@id='UM_WORK_DATE${index}']",
            'start': f"//*[@id='UM_TIME_IN${index}']",
            'end': f"//*[@id='UM_TIME_OUT${index}']",
            'break': f"//*[@id='UM_BREAK${index}']",
            'optional': f"//*[@id='UM_OPTIONAL_CD${index}']",
            'add_btn': f"//*[@id='COMPANY$new${index}$$0']"
        }
        
        # 1. Date
        date_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpaths['date'])))
        date_input.clear()
        date_input.send_keys(str(row["formatted_date"]))
        date_input.send_keys(Keys.TAB)
        sleep(timer)
        
        # 2. Start Time
        start_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpaths['start'])))
        start_input.clear()
        start_input.send_keys(str(row['start_time']))
        start_input.send_keys(Keys.TAB)
        sleep(timer)
        
        # 3. End Time
        end_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpaths['end'])))
        end_input.clear()
        end_input.send_keys(str(row['end_time']))
        end_input.send_keys(Keys.TAB)
        sleep(timer)
        
        # 4. Break
        break_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpaths['break'])))
        break_input.clear()
        break_input.send_keys("0")
        break_input.send_keys(Keys.TAB)
        sleep(timer)
        
        # # 5. Optional Code
        # optional_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpaths['optional'])))
        # optional_input.clear()
        # optional_input.send_keys(str(row['optional']))
        # optional_input.send_keys(Keys.TAB)
        # sleep(timer)
        
        # 6. Create Next Row
        if not is_last_row:
            add_row_btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpaths['add_btn'])))
            add_row_btn.click()
            sleep(timer)
            
            next_index = index + 1
            next_date_xpath = f"//*[@id='UM_WORK_DATE${next_index}']"
            self.wait.until(EC.presence_of_element_located((By.XPATH, next_date_xpath)))
            sleep(0.5)

    async def run(self, csv_file: str, timesheet_url: str) -> None:
        print("Processing")
        """Main orchestration method to read data and process the timesheet."""
        try:
            df = pd.read_csv(csv_file)
        except Exception as e:
            print(f"Failed to read CSV: {e}")
            return

        self.login_umbc(timesheet_url)

        choice = await questionary.select(
            "Finished Loading Page?",
            choices=["Yes"],
            use_indicator=True,
        ).ask_async()

        print("Entering timesheet data...")
        self._switch_to_peoplesoft_iframe()

        total_rows = len(df)
        for index, row in df.iterrows():
            is_last_row = (index + 1 == total_rows)
            self._enter_row_data(index=int(index), row=row, is_last_row=is_last_row)
            sleep(1)
            
        print("Finished submitting entries.")
        input("Press Enter to quit...")
        self.quit_driver()

    def quit_driver(self) -> None:
        if self.driver:
            self.driver.quit()
            print("Browser closed.")
