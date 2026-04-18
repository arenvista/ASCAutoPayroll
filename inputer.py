import os
import pandas as pd
from time import sleep
from typing import Optional, Any, Tuple
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
from dotenv import load_dotenv
import sys
import questionary

class TimesheetAutomator:
    """Automates UMBC timesheet entry using Selenium and Pandas."""

    def __init__(self, env_path: str = 'pass.env', profile_dir: str = "firefox_profile", wait_time: int = 15) -> None:
        self.env_path: str = env_path
        self.profile_dir: str = profile_dir
        self.wait_time: int = wait_time
        self.driver, self.wait = self._setup_driver()

    def _validate_setup(self) -> None:
        if self.driver is None or self.wait is None: self._setup_driver()
        if self.driver is None or self.wait is None: raise ValueError("Driver / Wait did not start properly")

    def _setup_driver(self) -> Tuple[webdriver.Firefox, WebDriverWait]:
        """Configures the Firefox profile and initializes the WebDriver."""
        print("Setting up Firefox profile in CWD...")
        options = Options()
        profile_path = os.path.join(os.getcwd(), self.profile_dir)
        options.add_argument("-profile")
        options.add_argument(profile_path)
        
        print(f"Using profile at: {profile_path}")
        print("Getting Driver...")
        driver: webdriver.Firefox = webdriver.Firefox(options=options)
        wait: WebDriverWait = WebDriverWait(driver, self.wait_time)
        return driver, wait

    def login_umbc(self, login_url: str) -> None:
        """Automates the initial login process."""
            
        load_dotenv(dotenv_path=os.path.join(os.getcwd(), self.env_path))
        username = os.getenv('UMBC_USR')
        password = os.getenv('UMBC_PAS')
        
        if not username or not password:
            print("Error: Missing credentials in .env file.")
            return

        print(f"Username => {username}\nPassword => {'*' * len(password)}")
        if login_url is None: raise ValueError("No Login URL")
        self.driver.get(login_url)

        try:
            uname_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="username"]')))
            uname_input.send_keys(username)
            
            pass_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="password"]')))
            pass_input.send_keys(password)
            
            self.driver.find_element(By.XPATH, '//*[@id="submitButton"]').click()
            sleep(10) # Allow time for redirection
        except TimeoutException:
            print("Login fields not found in time.")

    def _switch_to_peoplesoft_iframe(self) -> bool:
        """Locates and switches to the correct PeopleSoft iframe."""

        try:
            print("Switching to PeopleSoft iframe...")
            # Try the modal iframe first
            self.wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "ptModFrame_0")))
            print("Successfully switched to modal iframe (ptModFrame_0).")
            return True
        except TimeoutException:
            print("Modal iframe not found. Trying main content iframe...")
            try:
                # Fallback to the main target frame
                self.wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "ptifrmtgtframe")))
                print("Successfully switched to main iframe (ptifrmtgtframe).")
                return True
            except TimeoutException:
                print("Could not find either iframe. The script will likely fail.")
                return False

    def _enter_row_data(self, index: int, row: pd.Series, is_last_row: bool, timer: float = 0.5) -> None:
        """Inputs a single row of data from the DataFrame into the timesheet."""
        print(f"--- Row Index: {index} ---")
        
        # Define XPATHs for this specific row
        xpaths = {
            'date': f"//*[@id='UM_WORK_DATE${index}']",
            'start': f"//*[@id='UM_TIME_IN${index}']",
            'end': f"//*[@id='UM_TIME_OUT${index}']",
            'break': f"//*[@id='UM_BREAK${index}']",
            'optional': f"//*[@id='UM_OPTIONAL_CD${index}']",
            'add_btn': f"//*[@id='COMPANY$new${index}$$0']"
        }
        
        # 1. Date
        print("Waiting for and sending date...")
        date_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpaths['date'])))
        date_input.clear()
        date_input.send_keys(str(row["formatted_date"]))
        date_input.send_keys(Keys.TAB)
        sleep(timer)
        
        # 2. Start Time
        print("Sending start time...")
        start_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpaths['start'])))
        start_input.clear()
        start_input.send_keys(str(row['start_time']))
        start_input.send_keys(Keys.TAB)
        sleep(timer)
        
        # 3. End Time
        print("Sending end time...")
        end_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpaths['end'])))
        end_input.clear()
        end_input.send_keys(str(row['end_time']))
        end_input.send_keys(Keys.TAB)
        sleep(timer)
        
        # 4. Break
        print("Sending break time...")
        break_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpaths['break'])))
        break_input.clear()
        break_input.send_keys("0")
        break_input.send_keys(Keys.TAB)
        sleep(timer)
        
        # 5. Optional Code
        print("Sending optional code...")
        optional_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpaths['optional'])))
        optional_input.clear()
        optional_input.send_keys(str(row['optional']))
        optional_input.send_keys(Keys.TAB)
        sleep(timer)
        
        # 6. Create Next Row (if not the last record)
        print("Creating new entry row...")
        add_row_btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpaths['add_btn'])))
        add_row_btn.click()
        sleep(timer)
        
        if not is_last_row:
            print("Waiting for PeopleSoft to process the new row...")
            next_index = index + 1
            next_date_xpath = f"//*[@id='UM_WORK_DATE${next_index}']"
            self.wait.until(EC.presence_of_element_located((By.XPATH, next_date_xpath)))
            sleep(0.5) # Brief pause to ensure JavaScript event listeners have attached

    def run(self, csv_file: str, timesheet_url: str) -> None:
        """Main orchestration method to read data and process the timesheet."""
        if not self.driver or not self.wait:
            self._setup_driver()

        try:
            df = pd.read_csv(csv_file)
        except Exception as e:
            print(f"Failed to read CSV: {e}")
            return

        self.login_umbc(timesheet_url)

        print("Entering timesheet data...")
        self._switch_to_peoplesoft_iframe()

        # Iterate through data
        total_rows = len(df)
        for index, row in df.iterrows():
            is_last_row = (index + 1 == total_rows)
            self._enter_row_data(index=int(index), row=row, is_last_row=is_last_row)
            sleep(1)
            
        print("Finished submitting entries.")

        while input("Press Enter to quit, or 'z' to keep browser open: ").lower() != "z":
            break
        
        self.quit_driver()

    def quit_driver(self) -> None:
        """Safely closes the WebDriver."""
        if self.driver:
            self.driver.quit()
            print("Browser closed.")

def fuzzy_select_timeblock(csv_path='timeblocks.csv'):
    """
    Reads the timeblocks CSV and prompts the user with a fuzzy-searchable menu.
    Returns a tuple of (start_filter, end_filter).
    """
    try:
        # Load the timeblocks data
        blocks_df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"Error: Could not find {csv_path}. Make sure the file exists.")
        sys.exit(1)

    # Create a mapping dictionary for the menu options 
    # We use the period, start, and end columns to create a clean display string 
    choices_dict = {
        f"Period {row['period']:>2}: {row['start']} to {row['end']}": (row['start'], row['end'])
        for _, row in blocks_df.iterrows()
    }

    # Generate the interactive menu
    selected_display = questionary.select(
        "Fuzzy find and select a timeblock (type to filter/search):",
        choices=list(choices_dict.keys()),
        use_indicator=True, # Shows a pointer next to the selection
    ).ask()

    # Handle user cancellation (e.g., pressing Ctrl+C)
    if selected_display is None:
        print("\nSelection cancelled. Exiting.")
        sys.exit(0)

    # Return the (start, end) tuple associated with the chosen string
    return choices_dict[selected_display]

# ==========================================
# Main Execution Block
# ==========================================
if __name__ == "__main__":
    timeblock = fuzzy_select_timeblock()
    print(f"Selected => {timeblock}")

    CSV_FILENAME = f"{timeblock[0]}_{timeblock[1]}.csv"
    # CSV_FILENAME = "2026-03-08_2026-03-21.csv"
    TIMESHEET_PAGE = (
        "https://hrprd-web.pshr.umbc.edu/psp/ps/EMPLOYEE/HRMS/c/UM_ETS_EMP."
        "UM_ETS_EMP_SUMMARY.GBL?PORTALPARAM_PTCNAV=UM_ETS_EMP_SUMMARY_GBL&"
        "EOPP.SCNode=HRMS&EOPP.SCPortal=EMPLOYEE&EOPP.SCName=UMBC_TIME_ENTRY_LEAVE_PROCESS&"
        "EOPP.SCLabel=UMBC%20Time%20and%20Leave%20Processing&EOPP.SCPTfname=UMBC_TIME_ENTRY_LEAVE_PROCESS&"
        "FolderPath=PORTAL_ROOT_OBJECT.UMBC_TIME_ENTRY_LEAVE_PROCESS.UM_ETS_TIMESHEET.UM_ETS_EMP_SUMMARY_GBL&IsFolder=false"
    )

    automator = TimesheetAutomator()
    automator.run(csv_file=CSV_FILENAME, timesheet_url=TIMESHEET_PAGE)
