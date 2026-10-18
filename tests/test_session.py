from unittest import mock

import pytest
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

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
def test_login_uses_visible_form(
    legacy: bool,
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
    driver.find_element.return_value = greeting
    button.click.side_effect = lambda: setattr(greeting, "text", "Hi, Test")

    def find_elements(by: str, value: str) -> list[mock.MagicMock]:
        if "Necessary Only" in value:
            return [cookie_button]
        if by == By.CSS_SELECTOR:
            return [hidden_username, username]
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
