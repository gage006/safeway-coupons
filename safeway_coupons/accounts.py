from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Account:
    username: str
    password: str = field(repr=False)
    mail_to: str
    mail_from: str
    mail_from_name: Optional[str] = None
