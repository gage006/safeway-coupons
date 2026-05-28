import configparser
import itertools
import os
from typing import Optional

from .accounts import Account


class Config:
    @classmethod
    def load_accounts(
        cls,
        config_file: Optional[str] = None,
        mail_from_name: Optional[str] = None,
    ) -> list[Account]:
        account = cls.load_account_from_env(mail_from_name=mail_from_name)
        if account:
            return [account]
        if config_file:
            accounts = cls.load_accounts_from_config(
                config_file, mail_from_name=mail_from_name
            )
            if accounts:
                return accounts
        return []

    @classmethod
    def load_account_from_env(
        cls, mail_from_name: Optional[str] = None
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
            )
        return None

    @classmethod
    def load_accounts_from_config(
        cls, config_file: str, mail_from_name: Optional[str] = None
    ) -> list[Account]:
        config = configparser.ConfigParser()
        with open(config_file) as f:
            config.read_file(itertools.chain(["[_no_section]"], f))
        accounts: list[Account] = []
        mail_from = None
        mail_from_name_cfg = None
        for section in config.sections():
            if section in ["_no_section", "_global"]:
                if config.has_option(section, "email_sender"):
                    mail_from = config.get(section, "email_sender")
                if config.has_option(section, "email_sender_name"):
                    mail_from_name_cfg = config.get(
                        section, "email_sender_name"
                    )
                continue
            mail_to = (
                config.get(section, "notify")
                if config.has_option(section, "notify")
                else None
            )
            username = str(section)
            accounts.append(
                Account(
                    username=username,
                    password=config.get(section, "password"),
                    mail_to=mail_to or username,
                    mail_from=mail_from or username,
                    mail_from_name=mail_from_name_cfg or mail_from_name,
                )
            )
        return accounts
