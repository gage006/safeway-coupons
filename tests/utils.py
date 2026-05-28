from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from safeway_coupons.accounts import Account
from safeway_coupons.models import Offer, OfferStatus, OfferType


@dataclass
class ClipsTestConfig:
    fail_http_offer_ids: set[str] = field(default_factory=set)
    fail_response_offer_ids: set[str] = field(default_factory=set)
    clipped_offer_ids: list[str] = field(default_factory=list)
    failed_offer_ids: list[str] = field(default_factory=list)


def create_offer(offer_id: str, offer_price: str = "$99 OFF") -> Offer:
    return Offer(
        offer_id=offer_id,
        status=OfferStatus.Unclipped,
        name="Test Food",
        description="Test item for unit testing",
        start_date=datetime.now(timezone.utc) - timedelta(days=1),
        end_date=datetime.now(timezone.utc) + timedelta(days=1),
        offer_price=offer_price,
        offer_pgm=OfferType.PersonalizedDeal,
        category_type="Unit Test foods",
        image=(
            "https://www.safeway.com/CMS/j4u/offers/images/"
            f"test_{offer_id}.gif"
        ),
        image_id=f"test_{offer_id}",
    )


def create_account(mail_from_name: Optional[str] = None) -> Account:
    return Account(
        username="ness@onett.example",
        password="pk_fire",
        mail_from="ness@onett.example",
        mail_to="ness@onett.example",
        mail_from_name=mail_from_name,
    )
