import os
from pathlib import Path
from textwrap import dedent

import pytest
import pytest_mock

from safeway_coupons.config import Config


def test_env_mail_from_address(mocker: pytest_mock.MockerFixture) -> None:
    mocker.patch.object(
        os,
        "environ",
        {
            "SAFEWAY_ACCOUNT_USERNAME": "ness@onett.example",
            "SAFEWAY_ACCOUNT_PASSWORD": "pk_fire",
            "SAFEWAY_ACCOUNT_MAIL_FROM": "sender@onett.example",
        },
    )
    accounts = Config.load_accounts()
    assert len(accounts) == 1
    assert accounts[0].mail_from == "sender@onett.example"


def test_env_mail_from_name(mocker: pytest_mock.MockerFixture) -> None:
    mocker.patch.object(
        os,
        "environ",
        {
            "SAFEWAY_ACCOUNT_USERNAME": "ness@onett.example",
            "SAFEWAY_ACCOUNT_PASSWORD": "pk_fire",
            "SAFEWAY_ACCOUNT_MAIL_FROM_NAME": "Env Name",
        },
    )
    accounts = Config.load_accounts(mail_from_name="CLI Name")
    assert accounts[0].mail_from_name == "Env Name"


def test_env_mail_from_name_falls_back_to_cli(
    mocker: pytest_mock.MockerFixture,
) -> None:
    mocker.patch.object(
        os,
        "environ",
        {
            "SAFEWAY_ACCOUNT_USERNAME": "ness@onett.example",
            "SAFEWAY_ACCOUNT_PASSWORD": "pk_fire",
        },
    )
    accounts = Config.load_accounts(mail_from_name="CLI Name")
    assert accounts[0].mail_from_name == "CLI Name"


def test_config_email_sender_name(
    mocker: pytest_mock.MockerFixture, tmp_path: Path
) -> None:
    mocker.patch.object(os, "environ", {})
    cfg = tmp_path / "accounts"
    cfg.write_text(
        dedent(
            """\
            email_sender = sender@example.com
            email_sender_name = INI Name

            [safeway.account@example.com]
            password = 12345
            """
        )
    )
    accounts = Config.load_accounts(
        config_file=str(cfg), mail_from_name="CLI Name"
    )
    assert len(accounts) == 1
    assert accounts[0].mail_from == "sender@example.com"
    assert accounts[0].mail_from_name == "INI Name"


def test_config_email_sender_name_falls_back_to_cli(
    mocker: pytest_mock.MockerFixture, tmp_path: Path
) -> None:
    mocker.patch.object(os, "environ", {})
    cfg = tmp_path / "accounts"
    cfg.write_text(
        dedent(
            """\
            [safeway.account@example.com]
            password = 12345
            """
        )
    )
    accounts = Config.load_accounts(
        config_file=str(cfg), mail_from_name="CLI Name"
    )
    assert accounts[0].mail_from_name == "CLI Name"


def test_global_config_defaults(mocker: pytest_mock.MockerFixture) -> None:
    mocker.patch.object(os, "environ", {})
    gc = Config.load_global_config()
    assert gc.highlight_keywords_price == []
    assert gc.highlight_keywords_name == []
    assert gc.no_email_on_zero is False


def test_global_config_from_ini(
    mocker: pytest_mock.MockerFixture, tmp_path: Path
) -> None:
    mocker.patch.object(os, "environ", {})
    cfg = tmp_path / "accounts"
    cfg.write_text(
        dedent(
            """\
            highlight_keywords_price = FREE, BOGO
            highlight_keywords = Pepsi,Coke
            no_email_on_zero = true

            [safeway.account@example.com]
            password = 12345
            """
        )
    )
    gc = Config.load_global_config(config_file=str(cfg))
    assert gc.highlight_keywords_price == ["FREE", "BOGO"]
    assert gc.highlight_keywords_name == ["Pepsi", "Coke"]
    assert gc.no_email_on_zero is True


def test_global_config_from_ini_global_section(
    mocker: pytest_mock.MockerFixture, tmp_path: Path
) -> None:
    mocker.patch.object(os, "environ", {})
    cfg = tmp_path / "accounts"
    cfg.write_text(
        dedent(
            """\
            [_global]
            highlight_keywords_price = FREE
            highlight_keywords = Pepsi
            no_email_on_zero = yes

            [safeway.account@example.com]
            password = 12345
            """
        )
    )
    gc = Config.load_global_config(config_file=str(cfg))
    assert gc.highlight_keywords_price == ["FREE"]
    assert gc.highlight_keywords_name == ["Pepsi"]
    assert gc.no_email_on_zero is True


def test_global_config_env_overrides_ini_keywords(
    mocker: pytest_mock.MockerFixture, tmp_path: Path
) -> None:
    mocker.patch.object(
        os,
        "environ",
        {
            "SAFEWAY_HIGHLIGHT_KEYWORDS_PRICE": "HALFOFF",
            "SAFEWAY_HIGHLIGHT_KEYWORDS": "Sprite",
        },
    )
    cfg = tmp_path / "accounts"
    cfg.write_text(
        dedent(
            """\
            highlight_keywords_price = FREE
            highlight_keywords = Pepsi
            """
        )
    )
    gc = Config.load_global_config(config_file=str(cfg))
    assert gc.highlight_keywords_price == ["HALFOFF"]
    assert gc.highlight_keywords_name == ["Sprite"]


def test_global_config_empty_env_falls_back_to_ini(
    mocker: pytest_mock.MockerFixture, tmp_path: Path
) -> None:
    mocker.patch.object(
        os,
        "environ",
        {
            "SAFEWAY_HIGHLIGHT_KEYWORDS_PRICE": "",
            "SAFEWAY_HIGHLIGHT_KEYWORDS": "",
        },
    )
    cfg = tmp_path / "accounts"
    cfg.write_text(
        dedent(
            """\
            highlight_keywords_price = FREE
            highlight_keywords = Pepsi
            """
        )
    )
    gc = Config.load_global_config(config_file=str(cfg))
    assert gc.highlight_keywords_price == ["FREE"]
    assert gc.highlight_keywords_name == ["Pepsi"]


@pytest.mark.parametrize(
    ["ini_value", "env_value", "expected"],
    [
        ("false", None, False),
        ("true", None, True),
        ("false", "1", True),
        ("true", "0", True),
        (None, "yes", True),
        (None, None, False),
    ],
)
def test_global_config_no_email_on_zero_precedence(
    mocker: pytest_mock.MockerFixture,
    tmp_path: Path,
    ini_value: str,
    env_value: str,
    expected: bool,
) -> None:
    mocker.patch.object(
        os,
        "environ",
        {} if env_value is None else {"NO_EMAIL_ON_ZERO": env_value},
    )
    lines = ["[safeway.account@example.com]", "password = 12345"]
    if ini_value is not None:
        lines.insert(0, f"no_email_on_zero = {ini_value}")
    cfg = tmp_path / "accounts"
    cfg.write_text("\n".join(lines) + "\n")
    gc = Config.load_global_config(config_file=str(cfg))
    assert gc.no_email_on_zero is expected
