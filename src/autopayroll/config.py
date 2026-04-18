import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from autopayroll.data_gather.generate_time_blocks import TimeBlockGenerator

class ConfigSettings:
    def __init__(self) -> None:
        self.config_dir: Path = Path(os.path.expanduser('~/.config/autopayroll'))
        self.config_path: Path = self.config_dir / "settings.env"
        self.data_dir: Path = self.config_dir / "data"
        self.timeblock_path: Path = self.config_dir / "timeblock.env"
        self.html_file: Path = self.data_dir / "Attendance Listing.html"
        self.wait_time: int = 15
        
        self._check_config()
        self._read_config()
        self._check_missing()

    def _check_config(self):
        default_config="""
ENV_PATH=\"\"
ROOT_DIR=\"\"
PROFILE_DIR=\"\"
CONFIG_DIR=\"\"
CONFIG_PATH=\"\"
UMBC_USR=\"\"
UMBC_PAS=\"\"
"""
        if not self.config_dir.exists():
            print(f"Config dir does not exist: {self.config_dir} creating directory")
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)
            
        if not self.config_path.exists():
            print(f"Config file does not exist: {self.config_path} creating default")
            with open(self.config_path, "w") as config_file:
                config_file.write(default_config)
                
        if not self.timeblock_path.exists():
            print(f"Timeblock file does not exist: {self.timeblock_path} creating default")
            TimeBlockGenerator(str(self.timeblock_path)).run(start_filter="2026-03-22", end_filter="2026-04-04", n=10)

    def _read_config(self):
        load_dotenv(dotenv_path=self.config_path)
        self.umbc_usr:    Optional[str] = os.getenv("UMBC_USR")
        self.umbc_pass:   Optional[str] = os.getenv("UMBC_PAS")
        self.env_path:    Optional[str] = os.getenv("ENV_PATH")
        self.root_dir:    Optional[str] = os.getenv("ROOT_DIR")
        self.profile_dir: Optional[str] = os.getenv("PROFILE_DIR")

    def _check_missing(self):
        missing = [
            name for name, val in [
                ("PROFILE_DIR", self.profile_dir),
                ("UMBC_USR", self.umbc_usr),
                ("UMBC_PAS", self.umbc_pass)
            ] if val is None or val == ""
        ]

        if missing:
            print(f"Warning: Environment variable(s) not strictly set: {', '.join(missing)}")
