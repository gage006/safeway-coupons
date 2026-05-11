import contextlib
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import undetected_chromedriver as uc  # type: ignore

CHROMEDRIVER_PATH = (
    Path.home()
    / ".local"
    / "share"
    / "undetected_chromedriver"
    / "undetected_chromedriver"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)


class ChromeDriverDoesNotExist(Exception):
    pass


class ChromeDoesNotExist(Exception):
    pass


@contextlib.contextmanager
def chrome_driver(headless: bool = True) -> Iterator[uc.Chrome]:
    options = uc.ChromeOptions()
    options.headless = headless
    for option in [
        "--user-data-dir=" + str(Path.home()) + "/selenium-user-data",
        "--no-sandbox",
        "--disable-extensions",
        "--disable-application-cache",
        "--disable-gpu",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        f'--user-agent="{USER_AGENT}"',
    ]:
        options.add_argument(option)
    if headless:
        options.add_argument("--headless=new")
    version_match = re.findall(r"(\d+)\.", chrome_version())
    version_main = int(version_match[0]) if version_match else 0
    driver = uc.Chrome(options=options, version_main=version_main)
    yield driver
    driver.quit()


def chrome_version() -> str:
    chrome_path = Path("/usr/bin/google-chrome")
    if not chrome_path.is_file():
        raise ChromeDoesNotExist(f"Error: {chrome_path} does not exist")
    cmd = [str(chrome_path), "--version"]
    result = subprocess.run(cmd, capture_output=True)
    return result.stdout.decode()


def chrome_driver_version() -> str:
    if not CHROMEDRIVER_PATH.is_file():
        raise ChromeDriverDoesNotExist(
            f"Error: {CHROMEDRIVER_PATH} does not exist"
        )
    cmd = [str(CHROMEDRIVER_PATH), "--version"]
    print(f"+ {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True)
    return result.stdout.decode()


def init() -> None:
    print("Initializing Chrome Driver")
    with chrome_driver() as driver:
        print("Connect to example.com")
        driver.get("https://example.com")
    print(chrome_driver_version())
