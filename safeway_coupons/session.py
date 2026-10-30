import contextlib
import json
import select
import sys
import time
import urllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Optional

import requests
import undetected_chromedriver as uc  # type: ignore
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.remote.webdriver import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.wait import WebDriverWait

from .accounts import Account
from .chrome_driver import chrome_driver
from .errors import AuthenticationFailure


class ExceptionWithAttachments(Exception):
    def __init__(
        self,
        *args: Any,
        attachments: Optional[list[Path]] = None,
        **kwargs: Any,
    ):
        self.attachments = attachments


class BaseSession:
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    )

    @property
    def requests(self) -> requests.Session:
        if not hasattr(self, "_requests"):
            session = requests.Session()
            session.mount(
                "https://", requests.adapters.HTTPAdapter(pool_maxsize=1)
            )
            session.headers.update({"DNT": "1", "User-Agent": self.USER_AGENT})
            self._requests = session
        return self._requests


class LoginSession(BaseSession):
    SIGN_IN_TIMEOUT = 90

    def __init__(
        self,
        account: Account,
        interactive_sign_in: bool,
        debug_dir: Optional[Path],
    ) -> None:
        self.access_token: Optional[str] = None
        self.store_id: Optional[str] = None
        self.interactive_sign_in = interactive_sign_in
        self.debug_dir: Optional[Path] = debug_dir
        try:
            self._login(account)
        except ExceptionWithAttachments as e:
            raise AuthenticationFailure(
                e, account, attachments=e.attachments
            ) from e
        except Exception as e:
            raise AuthenticationFailure(e, account) from e

    @contextlib.contextmanager
    def _chrome_driver(self, headless: bool = True) -> Iterator[uc.Chrome]:
        try:
            with chrome_driver(headless=headless) as driver:
                yield driver
        except WebDriverException as e:
            attachments: list[Path] = []
            if self.debug_dir:
                path = self.debug_dir / "screenshot.png"
                with contextlib.suppress(WebDriverException, OSError):
                    self.debug_dir.mkdir(parents=True, exist_ok=True)
                    if driver.save_screenshot(str(path)):
                        attachments.append(path)
            raise ExceptionWithAttachments(
                f"[{type(e).__name__}] {e}", attachments=attachments
            ) from e
        finally:
            driver.quit()

    @staticmethod
    def _sign_in_success(driver: uc.Chrome) -> bool:
        try:
            element = driver.find_element(
                By.XPATH, '//span [contains(@class, "user-greeting")]'
            )
            if not (element and element.text):
                return False
            return not element.text.lower().startswith("sign in")
        except (StaleElementReferenceException, NoSuchElementException):
            return False

    @staticmethod
    def _element_exists(driver: uc.Chrome, id: str) -> bool:
        try:
            driver.find_element("id", id)
        except NoSuchElementException:
            return False
        return True

    @classmethod
    def _verification_required(cls, driver: uc.Chrome) -> bool:
        # The current modal no longer gives its verification form an ID.
        return any(
            cls._ready_element(driver, by, selector) is not None
            for by, selector in (
                (By.ID, "verifyOptionForm"),
                (
                    By.XPATH,
                    "//*[@id='modal-authenticate']//*[self::h1 or "
                    "self::h2][contains(., 'new device')]",
                ),
                (
                    By.CSS_SELECTOR,
                    "#modal-authenticate input[formcontrolname='otpCode']",
                ),
            )
        )

    def _session_ready(self, driver: uc.Chrome) -> bool:
        try:
            session = self._parse_cookie_value(
                driver.get_cookie("SWY_SHARED_SESSION")["value"]
            )
            info = self._parse_cookie_value(
                driver.get_cookie("SWY_SHARED_SESSION_INFO")["value"]
            )
            token = session["accessToken"]
            store = info["info"]["J4U"]["storeId"]
            return isinstance(token, str) and bool(token) and bool(store)
        except (TypeError, ValueError, KeyError):
            return False

    def _wait_for_sign_in(
        self, driver: uc.Chrome, allow_verification: bool = True
    ) -> None:
        def finished(browser: uc.Chrome) -> bool:
            # A visible challenge takes precedence over existing cookies.
            if self._verification_required(browser):
                return allow_verification
            return self._session_ready(browser)

        try:
            WebDriverWait(driver, self.SIGN_IN_TIMEOUT).until(
                finished,
                message="Waiting for sign-in session or device verification",
            )
        except TimeoutException as e:
            # Authentication can finish at the timeout boundary.
            if finished(driver):
                return
            if self._verification_required(driver):
                state = "verification required"
            elif any(
                driver.get_cookie(name)
                for name in ("SWY_SHARED_SESSION", "SWY_SHARED_SESSION_INFO")
            ):
                state = "session present but incomplete"
            else:
                state = "signed out (no session cookies)"
            raise TimeoutException(
                f"Sign-in did not finish within {self.SIGN_IN_TIMEOUT}s: "
                f"{state}. No credentials were resubmitted."
            ) from e

    @staticmethod
    def _ready_element(
        driver: uc.Chrome, by: str, value: str
    ) -> Optional[WebElement]:
        # Responsive pages may retain hidden copies of the login form.
        elements: list[WebElement] = driver.find_elements(by, value)
        for element in elements:
            try:
                if element.is_displayed() and element.is_enabled():
                    return element
            except StaleElementReferenceException:
                continue
        return None

    @classmethod
    def _wait_for_element(
        cls, driver: uc.Chrome, by: str, value: str, timeout: int = 30
    ) -> WebElement:
        element = WebDriverWait(driver, timeout).until(
            lambda browser: cls._ready_element(browser, by, value),
            message=f"Waiting for visible, enabled login control: {value}",
        )
        assert element is not None
        return element

    @classmethod
    def _wait_for_username(cls, driver: uc.Chrome) -> WebElement:
        # The sign-in URL can land on the storefront. Open its account
        # control (and, if present, the menu's sign-in link) before waiting
        # for the form. The header can appear before its click handler is
        # hydrated, so retry an unexpanded account menu after a grace period.
        clicked: list[WebElement] = []
        last_account_click: Optional[float] = None
        sign_in = (
            "//*[self::a or self::button or @role='button' or "
            "(self::span and contains(@class, 'user-greeting') and "
            "not(ancestor::*[self::a or self::button or @role='button']))]"
            "[translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz') = 'sign in' or "
            "translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz') = 'sign in / up']"
        )

        def find_username(browser: uc.Chrome) -> Optional[WebElement]:
            username = cls._ready_element(
                browser,
                By.CSS_SELECTOR,
                "input#label-email, input#enterUsername",
            )
            if username is not None:
                return username
            nonlocal last_account_click
            if len(clicked) < 2:
                controls = browser.find_elements(
                    By.XPATH, "//*[@id='auth_signin_link'] | " + sign_in
                )
                for control in controls:
                    try:
                        is_account = (
                            control.get_attribute("id") == "auth_signin_link"
                        )
                        if is_account and (
                            cls._ready_element(
                                browser, By.ID, "signin-dropdown"
                            )
                            is not None
                            or control.get_attribute("aria-expanded") == "true"
                            or (
                                last_account_click is not None
                                and time.monotonic() - last_account_click < 5
                            )
                        ):
                            # Safeway leaves aria-expanded=false even while
                            # the dropdown is visible. Do not toggle it shut.
                            continue
                        if (
                            control not in clicked
                            and control.is_displayed()
                            and control.is_enabled()
                        ):
                            control.click()
                            if is_account:
                                last_account_click = time.monotonic()
                            else:
                                clicked.append(control)
                            break
                    except StaleElementReferenceException:
                        continue
            return None

        username = WebDriverWait(driver, cls.SIGN_IN_TIMEOUT).until(
            find_username,
            message=(
                "Waiting for sign-in form after opening Sign in "
                "(before submitting credentials)"
            ),
        )
        assert username is not None
        return username

    @staticmethod
    def _get_code_from_human(timeout: int = 290, interval: int = 10) -> str:
        print(
            "Wait for the SMS OTP code and enter it here in the terminal "
            "(5 minute max): ",
            end="",
            flush=True,
        )
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if ready:
            return sys.stdin.readline().strip()
        else:
            raise Exception("Timeout waiting for OTP")

    def _login(self, account: Account) -> None:
        with self._chrome_driver() as driver:
            driver.implicitly_wait(0)
            url = "https://www.safeway.com/account/sign-in.html"
            print("Connect to safeway.com/account/sign-in.html")
            driver.get(url)
            try:
                button = self._wait_for_element(
                    driver,
                    By.XPATH,
                    "//button [contains(text(), 'Necessary Only')]",
                    timeout=5,
                )
                if button:
                    print("Decline cookie prompt")
                    button.click()
                    print(
                        "Return to safeway.com after declining cookie prompt"
                    )
                    driver.get(url)
            except TimeoutException:
                print("Skipping cookie prompt which is not present")
            time.sleep(2)

            # Check if already signed in
            print("Check if already signed in")
            if not self._sign_in_success(driver):
                print("Populate Sign In form")

                # Support new and old sign in flows
                username = self._wait_for_username(driver)
                username.send_keys(account.username)
                if username.get_attribute("id") == "label-email":
                    self._wait_for_element(
                        driver, By.ID, "label-password"
                    ).send_keys(account.password)
                    time.sleep(0.5)
                    print("Click Sign In button")
                    self._wait_for_element(driver, By.ID, "btnSignIn").click()
                else:
                    time.sleep(0.5)
                    print("Click Sign in with password button")
                    self._wait_for_element(
                        driver,
                        By.XPATH,
                        '//button[contains(text(), "Sign in with password")]',
                    ).click()
                    time.sleep(2)
                    print("Populate password")
                    self._wait_for_element(
                        driver, By.ID, "password"
                    ).send_keys(account.password)
                    time.sleep(0.5)
                    print("Click Sign In button")
                    self._wait_for_element(
                        driver,
                        By.XPATH,
                        '//button[contains(text(), "Sign In")]',
                    ).click()
                self._wait_for_sign_in(driver)

                # Check for verify device
                print("Check for verify device required")
                if self._verification_required(driver):
                    if not self.interactive_sign_in:
                        raise Exception(
                            "Interactive sign-in required, but not enabled."
                            " Run with --interactive-sign-in"
                        )
                    # Some sessions land directly on code entry.
                    if not self._ready_element(
                        driver,
                        By.CSS_SELECTOR,
                        "input[formcontrolname='otpCode']",
                    ):
                        print("Click Text code")
                        self._wait_for_element(
                            driver,
                            By.XPATH,
                            "//*[self::span or self::label]"
                            '[contains(text(), "Text code to")]',
                        ).click()
                        time.sleep(0.5)
                        print("Click Continue button")
                        self._wait_for_element(
                            driver,
                            By.XPATH,
                            '//button[contains(text(), "Continue")]',
                        ).click()

                    code = self._get_code_from_human()
                    print("Typing verification code")
                    self._wait_for_element(
                        driver, By.XPATH, '//input[@formcontrolname="otpCode"]'
                    ).send_keys(code)
                    time.sleep(0.5)
                    self._wait_for_element(
                        driver,
                        By.XPATH,
                        '//button[contains(text(), "Sign In")]',
                    ).click()

                # Check for sign in success
                print("Wait for signed-in session information")
                self._wait_for_sign_in(driver, allow_verification=False)

            print("Retrieve session information")
            session_cookie = self._parse_cookie_value(
                driver.get_cookie("SWY_SHARED_SESSION")["value"]
            )
            session_info_cookie = self._parse_cookie_value(
                driver.get_cookie("SWY_SHARED_SESSION_INFO")["value"]
            )
            self.access_token = session_cookie["accessToken"]
            try:
                self.store_id = session_info_cookie["info"]["J4U"]["storeId"]
            except Exception as e:
                raise Exception("Unable to retrieve store ID") from e

    def _parse_cookie_value(self, value: str) -> Any:
        return json.loads(urllib.parse.unquote(value))
