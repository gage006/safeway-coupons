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


def test_env_highlight_keywords(mocker: pytest_mock.MockerFixture) -> None:
    mocker.patch.object(
        os,
        "environ",
        {
            "SAFEWAY_ACCOUNT_USERNAME": "ness@onett.example",
            "SAFEWAY_ACCOUNT_PASSWORD": "pk_fire",
            "SAFEWAY_HIGHLIGHT_KEYWORDS_PRICE": "FREE, BOGO",
            "SAFEWAY_HIGHLIGHT_KEYWORDS": "Pepsi,Coke",
        },
    )
    accounts = Config.load_accounts()
    assert accounts[0].highlight_keywords_price == ["FREE", "BOGO"]
    assert accounts[0].highlight_keywords_name == ["Pepsi", "Coke"]


def test_config_highlight_keywords_global_default(
    mocker: pytest_mock.MockerFixture, tmp_path: Path
) -> None:
    mocker.patch.object(os, "environ", {})
    cfg = tmp_path / "accounts"
    cfg.write_text(
        dedent(
            """\
            highlight_keywords_price = FREE
            highlight_keywords = Pepsi, Coke

            [safeway.one@example.com]
            password = 1

            [safeway.two@example.com]
            password = 2
            """
        )
    )
    accounts = Config.load_accounts(config_file=str(cfg))
    assert len(accounts) == 2
    for account in accounts:
        assert account.highlight_keywords_price == ["FREE"]
        assert account.highlight_keywords_name == ["Pepsi", "Coke"]


def test_config_highlight_keywords_per_account_override(
    mocker: pytest_mock.MockerFixture, tmp_path: Path
) -> None:
    mocker.patch.object(os, "environ", {})
    cfg = tmp_path / "accounts"
    cfg.write_text(
        dedent(
            """\
            highlight_keywords_price = FREE

            [safeway.one@example.com]
            password = 1
            highlight_keywords_price = BOGO
            highlight_keywords = Pepsi

            [safeway.two@example.com]
            password = 2
            """
        )
    )
    accounts = {a.username: a for a in Config.load_accounts(str(cfg))}
    one = accounts["safeway.one@example.com"]
    two = accounts["safeway.two@example.com"]
    assert one.highlight_keywords_price == ["BOGO"]
    assert one.highlight_keywords_name == ["Pepsi"]
    # Account two inherits the top-level default and has no name keywords
    assert two.highlight_keywords_price == ["FREE"]
    assert two.highlight_keywords_name == []


def test_config_highlight_keywords_env_default(
    mocker: pytest_mock.MockerFixture, tmp_path: Path
) -> None:
    # Env-var keywords are the default when the config file omits them, but a
    # per-account config value overrides them.
    mocker.patch.object(
        os, "environ", {"SAFEWAY_HIGHLIGHT_KEYWORDS_PRICE": "FREE"}
    )
    cfg = tmp_path / "accounts"
    cfg.write_text(
        dedent(
            """\
            [safeway.one@example.com]
            password = 1

            [safeway.two@example.com]
            password = 2
            highlight_keywords_price = BOGO
            """
        )
    )
    accounts = {a.username: a for a in Config.load_accounts(str(cfg))}
    assert accounts["safeway.one@example.com"].highlight_keywords_price == [
        "FREE"
    ]
    assert accounts["safeway.two@example.com"].highlight_keywords_price == [
        "BOGO"
    ]


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


def test_global_config_explicit_section(tmp_path: Path) -> None:
    cfg = tmp_path / "accounts"
    cfg.write_text("[_global]\nno_email_on_zero = yes\n")
    assert Config.load_global_config(str(cfg)).no_email_on_zero is True
