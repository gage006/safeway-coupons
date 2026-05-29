import os
from pathlib import Path
from textwrap import dedent

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
