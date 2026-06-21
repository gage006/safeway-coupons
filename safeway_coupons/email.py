import collections
import mimetypes
import os
import re
import subprocess
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Optional

import jinja2

from .accounts import Account
from .errors import ClipError, Error, TooManyClipErrors
from .models import Offer, OfferType
from .report import ClipReport

_MAX_OFFERS_IN_EMAIL = 100

_jinja_env: Optional[jinja2.Environment] = None


def _get_jinja_env() -> jinja2.Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = jinja2.Environment(
            loader=jinja2.PackageLoader("safeway_coupons", "templates"),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
    return _jinja_env


def _keyword_pattern(
    keywords: list[str],
) -> Optional[re.Pattern[str]]:
    active = [k for k in keywords if k]
    if not active:
        return None
    return re.compile(
        r"\b(" + "|".join(re.escape(k) for k in active) + r")\b",
        re.IGNORECASE,
    )


def _offer_matches(
    offer: Offer,
    price_pattern: Optional[re.Pattern[str]],
    name_pattern: Optional[re.Pattern[str]],
) -> bool:
    if price_pattern and price_pattern.search(offer.offer_price):
        return True
    if name_pattern and (
        name_pattern.search(offer.name)
        or name_pattern.search(offer.description)
    ):
        return True
    return False


def _listed_offers(
    report: ClipReport,
) -> tuple[list[Offer], str]:
    price_pattern = _keyword_pattern(report.highlight_keywords_price)
    name_pattern = _keyword_pattern(report.highlight_keywords_name)
    if price_pattern or name_pattern:
        offers = [
            o
            for o in report.clipped
            if _offer_matches(o, price_pattern, name_pattern)
        ]
        all_kws = (
            report.highlight_keywords_price + report.highlight_keywords_name
        )
        label = f"Coupons matching {', '.join(all_kws)}"
    else:
        offers = list(report.clipped)
        label = "Clipped coupons"
    return offers, label


def _render_text(report: ClipReport) -> str:
    offers, section_header = _listed_offers(report)
    by_type: dict[OfferType, list[Offer]] = collections.defaultdict(list)
    for offer in report.clipped:
        by_type[offer.offer_pgm].append(offer)
    lines: list[str] = [
        f"Safeway account: {report.account.username}",
        f"Clipped {len(report.clipped)} total:",
    ]
    for offer_type, type_offers in by_type.items():
        lines.append(f"    {offer_type.name}: {len(type_offers)} coupons")
    price_pattern = _keyword_pattern(report.highlight_keywords_price)
    name_pattern = _keyword_pattern(report.highlight_keywords_name)
    if price_pattern or name_pattern:
        lines += ["", f"{section_header}:"]
        if offers:
            for offer in offers:
                lines.append(
                    f"[{offer.offer_price}] {offer.name}"
                    f" — {offer.offer_details_url}"
                )
        else:
            lines.append("  (no matches)")
    elif offers:
        lines += ["", f"{section_header}:"]
        for offer in offers:
            lines.append(
                f"[{offer.offer_price}] {offer.name}"
                f" — {offer.offer_details_url}"
            )
    return os.linesep.join(lines)


def _preheader(report: ClipReport) -> str:
    count = len(report.clipped)
    plural = "s" if count != 1 else ""
    base = f"{count} coupon{plural} clipped"
    all_kws = report.highlight_keywords_price + report.highlight_keywords_name
    if not all_kws:
        return base
    listed, _ = _listed_offers(report)
    kw_str = ", ".join(all_kws)
    match_count = len(listed)
    return f"{base} · {match_count} matching {kw_str}"


def _render_html(report: ClipReport) -> str:
    listed, section_label = _listed_offers(report)
    shown = listed[:_MAX_OFFERS_IN_EMAIL]
    overflow = max(0, len(listed) - _MAX_OFFERS_IN_EMAIL)

    by_type: dict[OfferType, list[Offer]] = collections.defaultdict(list)
    for offer in report.clipped:
        by_type[offer.offer_pgm].append(offer)

    price_pattern = _keyword_pattern(report.highlight_keywords_price)
    name_pattern = _keyword_pattern(report.highlight_keywords_name)
    expiring = report.expiring_soon
    if price_pattern or name_pattern:
        expiring = [
            o
            for o in expiring
            if _offer_matches(o, price_pattern, name_pattern)
        ]

    template = _get_jinja_env().get_template("clip_summary.html.j2")
    return template.render(
        account=report.account,
        clipped=report.clipped,
        preheader=_preheader(report),
        listed_offers=shown,
        overflow=overflow,
        section_label=section_label,
        by_type=by_type,
        expiring_soon=expiring,
    )


def _send_email(
    sendmail: list[str],
    account: Account,
    subject: str,
    text_body: str,
    debug_level: int,
    send_email: bool,
    html_body: Optional[str] = None,
    attachments: Optional[list[Path]] = None,
) -> None:
    if debug_level >= 1:
        if send_email:
            print(f"Sending email to {account.mail_to}")
        else:
            print(f"Would send email to {account.mail_to}")
        print(">>>>>>")
        print(text_body)
        print("<<<<<<")
    if not send_email:
        return
    msg = EmailMessage()
    msg["To"] = account.mail_to
    msg["From"] = (
        formataddr((account.mail_from_name, account.mail_from))
        if account.mail_from_name
        else account.mail_from
    )
    if subject:
        msg["Subject"] = subject
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    for attachment in attachments or []:
        mt = mimetypes.guess_type(attachment.name)[0]
        main, sub = mt.split("/", 1) if mt else ("application", "octet-stream")
        msg.add_attachment(
            attachment.read_bytes(),
            filename=attachment.name,
            maintype=main,
            subtype=sub,
        )
    p = subprocess.Popen(
        sendmail + ["-f", account.mail_to, "-t"], stdin=subprocess.PIPE
    )
    p.communicate(msg.as_bytes())


def email_clip_results(
    sendmail: list[str],
    account: Account,
    offers: list[Offer],
    error: Optional[Error],
    clip_errors: Optional[list[ClipError]],
    debug_level: int,
    send_email: bool,
    highlight_keywords_price: Optional[list[str]] = None,
    highlight_keywords_name: Optional[list[str]] = None,
) -> None:
    report = ClipReport(
        account=account,
        clipped=offers,
        clip_errors=clip_errors or [],
        error=error,
        highlight_keywords_price=highlight_keywords_price or [],
        highlight_keywords_name=highlight_keywords_name or [],
    )
    subject = f"Safeway coupons: {len(offers)} clipped"
    text_body = _render_text(report)
    html_body = _render_html(report)
    _send_email(
        sendmail,
        account,
        subject,
        text_body,
        debug_level,
        send_email,
        html_body=html_body,
    )


def email_error(
    sendmail: list[str],
    account: Account,
    error: Error,
    debug_level: int,
    send_email: bool,
) -> None:
    subject = f"Safeway coupons: {error.__class__.__name__} error"
    lines: list[str] = [
        f"Safeway account: {account.username}",
        f"Error: {error}",
    ]
    if isinstance(error, TooManyClipErrors) and error.clipped_offers:
        lines += ["", "Clipped coupons:"]
        for offer in error.clipped_offers:
            lines.append(str(offer))
    text_body = os.linesep.join(lines)
    _send_email(
        sendmail,
        account,
        subject,
        text_body,
        debug_level,
        send_email,
        attachments=getattr(error, "attachments", None),
    )
