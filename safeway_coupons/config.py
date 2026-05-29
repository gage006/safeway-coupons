import configparser
import itertools
import os
from typing import Optional

from .accounts import Account
from .utils import parse_keywords


class Config:
    @classmethod
    def load_accounts(
        cls,
        config_file: Optional[str] = None,
        mail_from_name: Optional[str] = None,
    ) -> list[Account]:
        # Highlight keywords from the environment act as a global default for
        # every account, regardless of the account source below. Per-account
        # config-file values take precedence over these.
        highlight_keywords_price = parse_keywords(
            os.environ.get("SAFEWAY_HIGHLIGHT_KEYWORDS_PRICE")
        )
        highlight_keywords_name = parse_keywords(
            os.environ.get("SAFEWAY_HIGHLIGHT_KEYWORDS")
        )
        account = cls.load_account_from_env(
            mail_from_name=mail_from_name,
            highlight_keywords_price=highlight_keywords_price,
            highlight_keywords_name=highlight_keywords_name,
        )
        if account:
            return [account]
        if config_file:
            accounts = cls.load_accounts_from_config(
                config_file,
                mail_from_name=mail_from_name,
                highlight_keywords_price=highlight_keywords_price,
                highlight_keywords_name=highlight_keywords_name,
            )
            if accounts:
                return accounts
        return []

    @classmethod
    def load_account_from_env(
        cls,
        mail_from_name: Optional[str] = None,
        highlight_keywords_price: Optional[list[str]] = None,
        highlight_keywords_name: Optional[list[str]] = None,
    ) -> Optional[Account]:
        username = os.environ.get("SAFEWAY_ACCOUNT_USERNAME")
        password = os.environ.get("SAFEWAY_ACCOUNT_PASSWORD")
        mail_to = os.environ.get("SAFEWAY_ACCOUNT_MAIL_TO")
        mail_from = os.environ.get("SAFEWAY_ACCOUNT_MAIL_FROM")
        if username and password:
            return Account(
                username=username,
                password=password,
                mail_to=mail_to or username,
                mail_from=mail_from or username,
                mail_from_name=os.environ.get("SAFEWAY_ACCOUNT_MAIL_FROM_NAME")
                or mail_from_name,
                highlight_keywords_price=highlight_keywords_price or [],
                highlight_keywords_name=highlight_keywords_name or [],
            )
        return None

    @classmethod
    def load_accounts_from_config(
        cls,
        config_file: str,
        mail_from_name: Optional[str] = None,
        highlight_keywords_price: Optional[list[str]] = None,
        highlight_keywords_name: Optional[list[str]] = None,
    ) -> list[Account]:
        config = configparser.ConfigParser()
        with open(config_file) as f:
            config.read_file(itertools.chain(["[_no_section]"], f))
        accounts: list[Account] = []
        mail_from = None
        mail_from_name_cfg = None
        # Top-level keyword keys override the environment default and in turn
        # act as the default for every account section below.
        default_keywords_price = highlight_keywords_price or []
        default_keywords_name = highlight_keywords_name or []
        for section in config.sections():
            if section in ["_no_section", "_global"]:
                if config.has_option(section, "email_sender"):
                    mail_from = config.get(section, "email_sender")
                if config.has_option(section, "email_sender_name"):
                    mail_from_name_cfg = config.get(
                        section, "email_sender_name"
                    )
                if config.has_option(section, "highlight_keywords_price"):
                    default_keywords_price = parse_keywords(
                        config.get(section, "highlight_keywords_price")
                    )
                if config.has_option(section, "highlight_keywords"):
                    default_keywords_name = parse_keywords(
                        config.get(section, "highlight_keywords")
                    )
                continue
            mail_to = (
                config.get(section, "notify")
                if config.has_option(section, "notify")
                else None
            )
            keywords_price = (
                parse_keywords(config.get(section, "highlight_keywords_price"))
                if config.has_option(section, "highlight_keywords_price")
                else default_keywords_price
            )
            keywords_name = (
                parse_keywords(config.get(section, "highlight_keywords"))
                if config.has_option(section, "highlight_keywords")
                else default_keywords_name
            )
            username = str(section)
            accounts.append(
                Account(
                    username=username,
                    password=config.get(section, "password"),
                    mail_to=mail_to or username,
                    mail_from=mail_from or username,
                    mail_from_name=mail_from_name_cfg or mail_from_name,
                    highlight_keywords_price=keywords_price,
                    highlight_keywords_name=keywords_name,
                )
            )
        return accounts
