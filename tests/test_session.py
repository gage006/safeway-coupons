from unittest import mock

import pytest
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

from safeway_coupons.errors import AuthenticationFailure
from safeway_coupons.session import LoginSession

from .utils import create_account

# conftest replaces until for most tests; exercise the real polling here.
REAL_UNTIL = WebDriverWait.until


def element(id: str, visible: bool = True) -> mock.MagicMock:
    result = mock.MagicMock()
    result.is_displayed.return_value = visible
    result.is_enabled.return_value = True
    result.get_attribute.return_value = id
    return result


def test_wait_ignores_hidden_disabled_and_stale_controls(
    mock_web_driver_wait: mock.MagicMock,
) -> None:
    driver = mock.MagicMock()
    hidden = element("username", visible=False)
    disabled = element("username")
    disabled.is_enabled.return_value = False
    stale = element("username")
    stale.is_displayed.side_effect = StaleElementReferenceException()
    ready = element("username")
    driver.find_elements.side_effect = [
        [hidden, disabled, stale],
        [hidden, ready],
    ]
    mock_web_driver_wait.side_effect = lambda condition, message: REAL_UNTIL(
        WebDriverWait(driver, 1, poll_frequency=0.001), condition, message
    )
    assert LoginSession._wait_for_element(driver, By.ID, "username") is ready
    assert driver.find_elements.call_count == 2


def test_wait_reports_missing_control(
    mock_web_driver_wait: mock.MagicMock,
) -> None:
    driver = mock.MagicMock()
    driver.find_elements.return_value = []
    mock_web_driver_wait.side_effect = lambda condition, message: REAL_UNTIL(
        WebDriverWait(driver, 0), condition, message
    )
    with pytest.raises(TimeoutException, match="login control: password"):
        LoginSession._wait_for_element(driver, By.ID, "password")


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("entry_steps", [0, 1, 2])
def test_login_uses_visible_form(
    legacy: bool,
    entry_steps: int,
    mock_undetected_chromedriver: mock.MagicMock,
    mock_web_driver_wait: mock.MagicMock,
) -> None:
    driver = mock_undetected_chromedriver
    username = element("label-email" if legacy else "enterUsername")
    hidden_username = element("label-email", visible=False)
    password = element("password")
    button = element("button")
    cookie_button = element("cookies")
    greeting = element("greeting")
    greeting.text = "Sign In"
    entry = element("sign-in")
    menu = element("sign-in-link")
    hidden_entry = element("mobile-sign-in", visible=False)
    driver.find_element.return_value = greeting
    button.click.side_effect = lambda: setattr(greeting, "text", "Hi, Test")

    def find_elements(by: str, value: str) -> list[mock.MagicMock]:
        if "Necessary Only" in value:
            return [cookie_button]
        if "new device" in value or "otpCode" in value:
            return []
        if by == By.CSS_SELECTOR:
            if (entry_steps == 1 and not entry.click.called) or (
                entry_steps == 2 and not menu.click.called
            ):
                return [hidden_username]
            return [hidden_username, username]
        if "translate(normalize-space" in value:
            if entry.click.called:
                return [hidden_entry, entry, menu]
            return [entry]
        if value in ("password", "label-password"):
            return [password]
        if value == "verifyOptionForm":
            return []
        return [button]

    driver.find_elements.side_effect = find_elements
    mock_web_driver_wait.side_effect = lambda condition, message: REAL_UNTIL(
        WebDriverWait(driver, 1, poll_frequency=0.001), condition, message
    )
    driver.get_cookie.side_effect = [
        {"value": '{"accessToken": "test_token"}'},
        {"value": '{"info": {"J4U": {"storeId": 42}}}'},
    ]
    account = create_account()
    session = LoginSession(account, False, None)
    username.send_keys.assert_called_once_with(account.username)
    hidden_username.send_keys.assert_not_called()
    password.send_keys.assert_called_once_with(account.password)
    assert session.access_token == "test_token"
    assert session.store_id == 42
    assert entry.click.call_count == int(entry_steps > 0)
    assert menu.click.call_count == int(entry_steps == 2)
    hidden_entry.click.assert_not_called()


@pytest.mark.parametrize("screen", ["legacy", "new-device", "code-entry"])
def test_detects_verification_screens(screen: str) -> None:
    driver = mock.MagicMock()

    def controls(by: str, value: str) -> list[mock.MagicMock]:
        matches = (
            (screen == "legacy" and value == "verifyOptionForm")
            or (screen == "new-device" and "new device" in value)
            or (screen == "code-entry" and "otpCode" in value)
        )
        return [element("verification")] if matches else []

    driver.find_elements.side_effect = controls
    assert LoginSession._verification_required(driver)


def test_hidden_verification_is_not_required() -> None:
    driver = mock.MagicMock()
    driver.find_elements.return_value = [element("old-modal", visible=False)]
    assert not LoginSession._verification_required(driver)


def test_new_verification_requires_interactive_sign_in(
    mock_undetected_chromedriver: mock.MagicMock,
) -> None:
    driver = mock_undetected_chromedriver
    driver.find_element.return_value.text = "Sign in"
    driver.find_elements.side_effect = lambda by, value: (
        [element("heading")] if "new device" in value else []
    )
    with pytest.raises(AuthenticationFailure, match="--interactive-sign-in"):
        LoginSession(create_account(), False, None)


def test_username_wait_does_not_repeatedly_toggle_sign_in(
    mock_web_driver_wait: mock.MagicMock,
) -> None:
    driver = mock.MagicMock()
    control = element("sign-in")
    driver.find_elements.side_effect = lambda by, value: (
        [] if by == By.CSS_SELECTOR else [control]
    )
    mock_web_driver_wait.side_effect = lambda condition, message: REAL_UNTIL(
        WebDriverWait(driver, 0.01, poll_frequency=0.001), condition, message
    )
    with pytest.raises(TimeoutException, match="Waiting for sign-in form"):
        LoginSession._wait_for_username(driver)
    control.click.assert_called_once()


@pytest.mark.parametrize("opens", [False, True])
def test_account_menu_retries_only_when_unexpanded(
    opens: bool,
    mock_web_driver_wait: mock.MagicMock,
) -> None:
    driver = mock.MagicMock()
    control = element("auth_signin_link")
    control.get_attribute.side_effect = lambda name: (
        "auth_signin_link"
        if name == "id"
        else "true" if opens and control.click.called else "false"
    )
    driver.find_elements.side_effect = lambda by, value: (
        [] if by == By.CSS_SELECTOR else [control]
    )

    def poll(condition: object, message: str) -> None:
        # Simulate a header rendered before its event handler is attached.
        for _ in range(8):
            condition(driver)  # type: ignore[operator]
        raise TimeoutException(message)

    mock_web_driver_wait.side_effect = poll
    with mock.patch(
        "safeway_coupons.session.time.monotonic", side_effect=range(0, 200, 6)
    ):
        pytest.raises(
            TimeoutException, LoginSession._wait_for_username, driver
        )
    assert control.click.call_count == (1 if opens else 3)
