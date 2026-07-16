import os
import sys
from enum import Enum
import questionary
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait

from autopayroll.config import ConfigSettings 
from autopayroll.handler import Handler 

# CORRECTED: Pointing to the specific files inside the submodules
from autopayroll.auto_insert.inputer import TimesheetAutomator 
from autopayroll.data_preprocess.parser import AttendanceParser 
from autopayroll.data_gather.pull_sheet import UMBCTimesheetScraper

class ControlFlow(Enum):
    EXIT = 0
    PROCESS = 1

class Interface:
    def __init__(self) -> None:
        self.config = ConfigSettings()
        self.handler = Handler(self.config.timeblock_path)
        self._setup_driver()
        self.timesheet_mgr = TimesheetAutomator(self.driver, self.wait, self.config)

    def _setup_driver(self) -> None:
        """Configures and initializes the Firefox WebDriver."""
        print(f"Setting up Firefox profile at: {self.config.profile_dir}")
        options: Options = Options()
        if self.config.profile_dir:
            options.add_argument("-profile")
            options.add_argument(str(self.config.profile_dir))

        print("Initializing WebDriver...")
        self.driver = webdriver.Firefox(options=options)
        self.wait: WebDriverWait = WebDriverWait(self.driver, self.config.wait_time)

    async def _process_timesheet(self):
        timeblock = await self.handler.select_timeblock()
        TIMESHEET_PAGE = (
            "https://hrprd-web.pshr.umbc.edu/psp/ps/EMPLOYEE/HRMS/c/UM_ETS_EMP."
            "UM_ETS_EMP_SUMMARY.GBL?PORTALPARAM_PTCNAV=UM_ETS_EMP_SUMMARY_GBL&"
            "EOPP.SCNode=HRMS&EOPP.SCPortal=EMPLOYEE&EOPP.SCName=UMBC_TIME_ENTRY_LEAVE_PROCESS&"
            "EOPP.SCLabel=UMBC%20Time%20and%20Leave%20Processing&EOPP.SCPTfname=UMBC_TIME_ENTRY_LEAVE_PROCESS&"
            "FolderPath=PORTAL_ROOT_OBJECT.UMBC_TIME_ENTRY_LEAVE_PROCESS.UM_ETS_TIMESHEET.UM_ETS_EMP_SUMMARY_GBL&IsFolder=false"
        )
        
        CSV_FILEPATH = self.config.data_dir / f"{timeblock[0]}_{timeblock[1]}.csv"
        
        print("[GETTING LATEST TIMESHEET]")
        scraper = UMBCTimesheetScraper(self.driver, self.config)
        await scraper.run()

        print(f"[PARSING NEW TIMEBLOCK] => {timeblock[0]} to {timeblock[1]}...")
        parser = AttendanceParser(html_file=self.config.html_file, timeblocks_file=self.config.timeblock_path)
        parser.run(timeblock[0], timeblock[1], self.config.data_dir)
            
        await self.timesheet_mgr.run(str(CSV_FILEPATH), TIMESHEET_PAGE)

    def _process_exit(self):
        print("\nExiting. Goodbye!")
        if hasattr(self, 'driver') and self.driver:
            self.driver.quit()
        sys.exit(0)

    async def _process_request(self, request: ControlFlow):
        match request:
            case ControlFlow.PROCESS:
                return await self._process_timesheet()
            case ControlFlow.EXIT:
                return self._process_exit()
            case _:
                raise Exception('Unknown exception occurred')

    async def main(self):
            """Main menu loop."""
            scripts = {
                "1.  Process a Timesheet": ControlFlow.PROCESS,
                "2. 󰈆 Exit": ControlFlow.EXIT
            }

            while True:
                # CHANGE: Use await and .ask_async() here
                choice = await questionary.select(
                    "What would you like to do?",
                    choices=list(scripts.keys()),
                    use_indicator=True
                ).ask_async()

                await self._process_request(scripts[choice])
if __name__ == "__main__":
    import asyncio
    asyncio.run(Interface().main())
