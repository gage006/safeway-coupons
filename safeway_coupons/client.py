import json
import random
from pathlib import Path
from typing import Optional

import requests

from .accounts import Account
from .errors import ClipError, HTTPError
from .methods import ClipRequest, ClipResponse
from .models import Offer, OfferList
from .session import BaseSession, LoginSession


class SafewayClient(BaseSession):
    def __init__(
        self,
        account: Account,
        interactive_sign_in: bool,
        debug_dir: Optional[Path],
    ) -> None:
        self.session = LoginSession(account, interactive_sign_in, debug_dir)
        self.debug_dir = debug_dir
        self.requests.headers.update(
            {
                "Authorization": f"Bearer {self.session.access_token}",
                "X-SW" "Y_AP" "I_K" "EY": "em" "j" "ou",
                "X-SW" "Y_VERSION": "1.1",
                "X-SW" "Y-APPLICATION-TYPE": "web",
            }
        )

    def get_offers(self) -> list[Offer]:
        try:
            response = self.requests.get(
                "https://www.safeway.com/abs/pub/xapi"
                "/offers/companiongalleryoffer"
                f"?storeId={self.session.store_id}"
                f"&rand={random.randrange(100000, 999999)}"
            )
            response.raise_for_status()
            if self.debug_dir:
                (self.debug_dir / "offers.json").write_text(response.text)
            offers_dict = OfferList.from_dict(response.json()).offers
            return list(offers_dict.values())
        except requests.exceptions.HTTPError as e:
            raise HTTPError(e, response) from e

    def fetch_offer_images(self, offers: list[Offer]) -> dict[str, bytes]:
        candidates = [o for o in offers if o.image]
        if not candidates:
            return {}
        images: dict[str, bytes] = {}
        consecutive_failures = 0
        first_error: Optional[str] = None
        # Coupon images are static website content behind the WAF, not the
        # bearer-token API tier, so fetch them with the browser cookies
        # harvested at login and ordinary image-request headers.
        with requests.Session() as image_session:
            image_session.headers.update(
                {
                    "User-Agent": self.USER_AGENT,
                    "DNT": "1",
                    "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
                    "Referer": (
                        "https://www.safeway.com/foru/coupons-deals.html"
                    ),
                }
            )
            for cookie in self.session.cookies:
                image_session.cookies.set(
                    cookie["name"],
                    cookie["value"],
                    domain=cookie.get("domain", ""),
                    path=cookie.get("path", "/"),
                )
            for offer in candidates:
                try:
                    resp = image_session.get(offer.image, timeout=10)
                    resp.raise_for_status()
                    images[offer.offer_id] = resp.content
                    consecutive_failures = 0
                except requests.exceptions.RequestException as e:
                    consecutive_failures += 1
                    if first_error is None:
                        first_error = str(e)
                    if not images and consecutive_failures >= 5:
                        break
        print(
            f"Fetched {len(images)}/{len(candidates)} coupon images for email"
        )
        if first_error and len(images) < len(candidates):
            print(f"  Example image fetch failure: {first_error}")
        return images

    def clip(self, offer: Offer) -> None:
        request = ClipRequest.from_offer(offer)
        response: Optional[requests.Response] = None
        try:
            response = self.requests.post(
                "https://www.safeway.com/abs/pub/web/j4u/api/offers/clip"
                f"?storeId={self.session.store_id}",
                data=json.dumps(request.to_dict(encode_json=True)),
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            clip_response = ClipResponse.from_dict(response.json())
            if not clip_response.success:
                raise Exception(
                    f"Unsuccessful clip response for coupon {offer}"
                )
        except Exception as e:
            raise ClipError(e, response, offer) from e
