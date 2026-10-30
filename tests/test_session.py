from unittest import mock

import pytest
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

from safeway_coupons.errors import AuthenticationFailure
from safeway_coupons.session import ExceptionWithAttachments, LoginSession

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
    driver.get_cookie.side_effect = {
        "SWY_SHARED_SESSION": {"value": '{"accessToken": "test_token"}'},
        "SWY_SHARED_SESSION_INFO": {
            "value": '{"info": {"J4U": {"storeId": 42}}}'
        },
    }.get
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
        [] if by in (By.CSS_SELECTOR, By.ID) else [control]
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
        [] if by in (By.CSS_SELECTOR, By.ID) else [control]
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
    assert control.click.call_count == (1 if opens else 8)


@pytest.mark.parametrize("rerender", [False, True])
def test_delayed_account_menu_with_incorrect_expanded_attribute(
    rerender: bool,
    mock_web_driver_wait: mock.MagicMock,
) -> None:
    driver = mock.MagicMock()
    account = element("auth_signin_link")
    account.get_attribute.side_effect = lambda name: (
        "auth_signin_link" if name == "id" else "false"
    )
    menu = element("signin-dropdown")
    sign_in = element("sign-in")
    username = element("enterUsername")
    attempts = 0

    def open_menu() -> None:
        nonlocal attempts
        attempts += 1

    account.click.side_effect = open_menu

    def controls(by: str, value: str) -> list[mock.MagicMock]:
        if by == By.CSS_SELECTOR:
            return [username] if sign_in.click.called else []
        if value == "signin-dropdown":
            return [menu] if attempts >= 4 else []
        # Hydration can replace the header element after an ignored click.
        header = mock.MagicMock(wraps=account) if rerender else account
        return [header, sign_in] if attempts >= 4 else [header]

    driver.find_elements.side_effect = controls

    def poll(condition: object, message: str) -> object:
        for _ in range(8):
            result = condition(driver)  # type: ignore[operator]
            if result is not None:
                return result
        raise TimeoutException(message)

    mock_web_driver_wait.side_effect = poll
    with mock.patch(
        "safeway_coupons.session.time.monotonic", side_effect=range(0, 200, 6)
    ):
        assert LoginSession._wait_for_username(driver) is username
    assert attempts == 4
    sign_in.click.assert_called_once()


def session_for_wait() -> LoginSession:
    return LoginSession.__new__(LoginSession)


def test_session_cookies_work_before_greeting() -> None:
    driver = mock.MagicMock()
    driver.find_elements.return_value = []
    driver.find_element.return_value.text = "Sign in"
    driver.get_cookie.side_effect = {
        "SWY_SHARED_SESSION": {"value": '{"accessToken":"token"}'},
        "SWY_SHARED_SESSION_INFO": {
            "value": '{"info":{"J4U":{"storeId":42}}}'
        },
    }.get
    session = session_for_wait()
    assert session._session_ready(driver)
    assert not session._sign_in_success(driver)


@pytest.mark.parametrize(
    "value", [None, "bad-json", "{}", '{"accessToken":""}']
)
def test_incomplete_session_not_ready(value: object) -> None:
    driver = mock.MagicMock()
    driver.get_cookie.return_value = (
        None if value is None else {"value": value}
    )
    assert not session_for_wait()._session_ready(driver)


def test_delayed_sign_in_uses_90_second_wait(
    mock_web_driver_wait: mock.MagicMock,
) -> None:
    session = session_for_wait()
    driver = mock.MagicMock()
    driver.find_elements.return_value = []
    with mock.patch.object(
        session, "_session_ready", side_effect=[False, False, True]
    ):

        def poll(condition: object, message: str) -> None:
            assert not condition(driver)  # type: ignore[operator]
            assert not condition(driver)  # type: ignore[operator]
            assert condition(driver)  # type: ignore[operator]

        mock_web_driver_wait.side_effect = poll
        with mock.patch(
            "safeway_coupons.session.WebDriverWait", wraps=WebDriverWait
        ) as wait:
            session._wait_for_sign_in(driver)
        wait.assert_called_once_with(driver, 90)


def test_final_session_check_recovers_timeout(
    mock_web_driver_wait: mock.MagicMock,
) -> None:
    session = session_for_wait()
    driver = mock.MagicMock()
    driver.find_elements.return_value = []
    mock_web_driver_wait.side_effect = TimeoutException()
    with mock.patch.object(session, "_session_ready", return_value=True):
        session._wait_for_sign_in(driver)


@pytest.mark.parametrize("partial", [False, True])
def test_timeout_reports_session_state(
    partial: bool,
    mock_web_driver_wait: mock.MagicMock,
) -> None:
    session = session_for_wait()
    driver = mock.MagicMock()
    driver.find_elements.return_value = []
    driver.get_cookie.return_value = {"value": "{}"} if partial else None
    mock_web_driver_wait.side_effect = TimeoutException()
    state = "session present but incomplete" if partial else "signed out"
    with pytest.raises(TimeoutException, match=state):
        session._wait_for_sign_in(driver)


def test_verification_takes_precedence_over_cookies(
    mock_web_driver_wait: mock.MagicMock,
) -> None:
    session = session_for_wait()
    driver = mock.MagicMock()
    driver.find_elements.return_value = [element("verification")]
    with mock.patch.object(
        session, "_session_ready", return_value=True
    ) as ready:
        mock_web_driver_wait.side_effect = (
            lambda condition, message: condition(driver)
        )
        session._wait_for_sign_in(driver)
        ready.assert_not_called()
        mock_web_driver_wait.side_effect = TimeoutException()
        with pytest.raises(TimeoutException, match="verification required"):
            session._wait_for_sign_in(driver, allow_verification=False)


def test_timeout_saves_screenshot(
    tmp_path: object,
    mock_undetected_chromedriver: mock.MagicMock,
) -> None:
    from pathlib import Path

    session = session_for_wait()
    session.debug_dir = Path(str(tmp_path)) / "diagnostics"
    driver = mock_undetected_chromedriver
    driver.save_screenshot.return_value = True
    with (
        pytest.raises(ExceptionWithAttachments) as error,
        session._chrome_driver(),
    ):
        raise TimeoutException("session present but incomplete")
    assert error.value.attachments == [session.debug_dir / "screenshot.png"]
    driver.save_screenshot.assert_called_once_with(
        str(session.debug_dir / "screenshot.png")
    )
    assert session.debug_dir.is_dir()
