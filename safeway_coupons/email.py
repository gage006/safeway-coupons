import collections
import mimetypes
import os
import re
import subprocess
from email.message import EmailMessage
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


def _listed_offers(
    report: ClipReport,
) -> tuple[list[Offer], str]:
    pattern = _keyword_pattern(report.highlight_keywords)
    if pattern:
        offers = [o for o in report.clipped if pattern.search(o.offer_price)]
        label = f"Coupons matching {', '.join(report.highlight_keywords)}"
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
    if offers:
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
    parts = [f"{count} coupon{plural} clipped"]
    if report.clipped:
        first = report.clipped[0]
        parts.append(f"{first.offer_price} {first.name}")
    return " - ".join(parts)


def _render_html(report: ClipReport) -> str:
    listed, section_label = _listed_offers(report)
    shown = listed[:_MAX_OFFERS_IN_EMAIL]
    overflow = max(0, len(listed) - _MAX_OFFERS_IN_EMAIL)

    by_type: dict[OfferType, list[Offer]] = collections.defaultdict(list)
    for offer in report.clipped:
        by_type[offer.offer_pgm].append(offer)

    pattern = _keyword_pattern(report.highlight_keywords)
    expiring = report.expiring_soon
    if pattern:
        expiring = [o for o in expiring if pattern.search(o.offer_price)]

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
    msg["From"] = account.mail_from
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
    highlight_keywords: Optional[list[str]] = None,
) -> None:
    report = ClipReport(
        account=account,
        clipped=offers,
        clip_errors=clip_errors or [],
        error=error,
        highlight_keywords=highlight_keywords or [],
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
