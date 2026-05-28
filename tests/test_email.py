import pytest_mock

from safeway_coupons import email as email_mod
from safeway_coupons.email import _send_email, email_clip_results

from .utils import create_account, create_offer


def test_from_header_includes_display_name(
    mocker: pytest_mock.MockerFixture,
) -> None:
    popen = mocker.patch.object(email_mod.subprocess, "Popen")
    _send_email(
        sendmail=["/usr/sbin/sendmail"],
        account=create_account(mail_from_name="Safeway Coupons"),
        subject="Test",
        text_body="body",
        debug_level=0,
        send_email=True,
    )
    sent = popen.return_value.communicate.call_args.args[0]
    assert b"From: Safeway Coupons <ness@onett.example>" in sent


def test_from_header_bare_address_without_name(
    mocker: pytest_mock.MockerFixture,
) -> None:
    popen = mocker.patch.object(email_mod.subprocess, "Popen")
    _send_email(
        sendmail=["/usr/sbin/sendmail"],
        account=create_account(),
        subject="Test",
        text_body="body",
        debug_level=0,
        send_email=True,
    )
    sent = popen.return_value.communicate.call_args.args[0]
    assert b"From: ness@onett.example" in sent
    assert b"<ness@onett.example>" not in sent


def test_lists_all_offers_when_no_keywords(
    mocker: pytest_mock.MockerFixture,
) -> None:
    send_mock = mocker.patch.object(email_mod, "_send_email")
    offers = [
        create_offer("1", offer_price="$5 OFF"),
        create_offer("2", offer_price="FREE"),
        create_offer("3", offer_price="Buy 1 Get 1 FREE"),
    ]
    email_clip_results(
        sendmail=["/usr/sbin/sendmail"],
        account=create_account(),
        offers=offers,
        error=None,
        clip_errors=None,
        debug_level=0,
        send_email=False,
    )
    body = send_mock.call_args.args[3]
    for offer in offers:
        assert offer.offer_details_url in body
    assert "Clipped coupons:" in body


def test_filters_to_keyword_match(
    mocker: pytest_mock.MockerFixture,
) -> None:
    send_mock = mocker.patch.object(email_mod, "_send_email")
    free_one = create_offer("1", offer_price="FREE")
    not_free = create_offer("2", offer_price="$5 OFF")
    free_two = create_offer("3", offer_price="Buy 1 Get 1 FREE")
    email_clip_results(
        sendmail=["/usr/sbin/sendmail"],
        account=create_account(),
        offers=[free_one, not_free, free_two],
        error=None,
        clip_errors=None,
        debug_level=0,
        send_email=False,
        highlight_keywords=["FREE"],
    )
    body = send_mock.call_args.args[3]
    assert free_one.offer_details_url in body
    assert free_two.offer_details_url in body
    assert not_free.offer_details_url not in body
    assert "Coupons matching FREE:" in body


def test_keyword_match_is_case_insensitive(
    mocker: pytest_mock.MockerFixture,
) -> None:
    send_mock = mocker.patch.object(email_mod, "_send_email")
    offer = create_offer("1", offer_price="free with purchase")
    email_clip_results(
        sendmail=["/usr/sbin/sendmail"],
        account=create_account(),
        offers=[offer],
        error=None,
        clip_errors=None,
        debug_level=0,
        send_email=False,
        highlight_keywords=["FREE"],
    )
    body = send_mock.call_args.args[3]
    assert offer.offer_details_url in body


def test_keyword_match_is_word_bounded(
    mocker: pytest_mock.MockerFixture,
) -> None:
    send_mock = mocker.patch.object(email_mod, "_send_email")
    offer = create_offer("1", offer_price="FREEZER PROMO $2 OFF")
    email_clip_results(
        sendmail=["/usr/sbin/sendmail"],
        account=create_account(),
        offers=[offer],
        error=None,
        clip_errors=None,
        debug_level=0,
        send_email=False,
        highlight_keywords=["FREE"],
    )
    body = send_mock.call_args.args[3]
    assert offer.offer_details_url not in body


def test_subject_unchanged_with_filter(
    mocker: pytest_mock.MockerFixture,
) -> None:
    send_mock = mocker.patch.object(email_mod, "_send_email")
    offers = [
        create_offer("1", offer_price="FREE"),
        create_offer("2", offer_price="$5 OFF"),
        create_offer("3", offer_price="$3 OFF"),
    ]
    email_clip_results(
        sendmail=["/usr/sbin/sendmail"],
        account=create_account(),
        offers=offers,
        error=None,
        clip_errors=None,
        debug_level=0,
        send_email=False,
        highlight_keywords=["FREE"],
    )
    subject = send_mock.call_args.args[2]
    assert subject == "Safeway coupons: 3 clipped"


def test_html_alternative_included(
    mocker: pytest_mock.MockerFixture,
) -> None:
    send_mock = mocker.patch.object(email_mod, "_send_email")
    offer = create_offer("42", offer_price="$2 OFF")
    email_clip_results(
        sendmail=["/usr/sbin/sendmail"],
        account=create_account(),
        offers=[offer],
        error=None,
        clip_errors=None,
        debug_level=0,
        send_email=False,
    )
    # html_body is the html_body kwarg
    html_body = send_mock.call_args.kwargs.get("html_body")
    assert html_body is not None
    assert "<!DOCTYPE html>" in html_body
    assert offer.offer_details_url in html_body
    assert offer.offer_price in html_body
    assert offer.name in html_body


def test_html_contains_offer_details_link(
    mocker: pytest_mock.MockerFixture,
) -> None:
    send_mock = mocker.patch.object(email_mod, "_send_email")
    offer = create_offer("99", offer_price="FREE")
    email_clip_results(
        sendmail=["/usr/sbin/sendmail"],
        account=create_account(),
        offers=[offer],
        error=None,
        clip_errors=None,
        debug_level=0,
        send_email=False,
    )
    html_body = send_mock.call_args.kwargs.get("html_body")
    assert html_body is not None
    assert "offer-details.99.PD.html" in html_body


def test_html_uses_offer_image_url(
    mocker: pytest_mock.MockerFixture,
) -> None:
    send_mock = mocker.patch.object(email_mod, "_send_email")
    offer = create_offer("42", offer_price="$2 OFF")
    email_clip_results(
        sendmail=["/usr/sbin/sendmail"],
        account=create_account(),
        offers=[offer],
        error=None,
        clip_errors=None,
        debug_level=0,
        send_email=False,
    )
    html_body = send_mock.call_args.kwargs.get("html_body")
    assert html_body is not None
    assert (
        "https://images.albertsons-media.com/is/image/ABS/test_42" in html_body
    )
    assert offer.image not in html_body


def test_html_respects_keyword_filter(
    mocker: pytest_mock.MockerFixture,
) -> None:
    send_mock = mocker.patch.object(email_mod, "_send_email")
    free_offer = create_offer("1", offer_price="FREE")
    paid_offer = create_offer("2", offer_price="$3 OFF")
    email_clip_results(
        sendmail=["/usr/sbin/sendmail"],
        account=create_account(),
        offers=[free_offer, paid_offer],
        error=None,
        clip_errors=None,
        debug_level=0,
        send_email=False,
        highlight_keywords=["FREE"],
    )
    html_body = send_mock.call_args.kwargs.get("html_body")
    assert html_body is not None
    assert free_offer.offer_details_url in html_body
    assert paid_offer.offer_details_url not in html_body


def test_html_disables_ios_data_detectors(
    mocker: pytest_mock.MockerFixture,
) -> None:
    send_mock = mocker.patch.object(email_mod, "_send_email")
    email_clip_results(
        sendmail=["/usr/sbin/sendmail"],
        account=create_account(),
        offers=[create_offer("1", offer_price="$2 OFF")],
        error=None,
        clip_errors=None,
        debug_level=0,
        send_email=False,
    )
    html_body = send_mock.call_args.kwargs.get("html_body")
    assert html_body is not None
    assert 'name="format-detection"' in html_body
    assert "a[x-apple-data-detectors]" in html_body


def test_html_includes_preheader(
    mocker: pytest_mock.MockerFixture,
) -> None:
    send_mock = mocker.patch.object(email_mod, "_send_email")
    email_clip_results(
        sendmail=["/usr/sbin/sendmail"],
        account=create_account(),
        offers=[
            create_offer("1", offer_price="$2 OFF"),
            create_offer("2", offer_price="FREE"),
        ],
        error=None,
        clip_errors=None,
        debug_level=0,
        send_email=False,
    )
    html_body = send_mock.call_args.kwargs.get("html_body")
    assert html_body is not None
    assert "2 coupons clipped" in html_body


def test_html_uses_larger_thumbnail(
    mocker: pytest_mock.MockerFixture,
) -> None:
    send_mock = mocker.patch.object(email_mod, "_send_email")
    email_clip_results(
        sendmail=["/usr/sbin/sendmail"],
        account=create_account(),
        offers=[create_offer("1", offer_price="$2 OFF")],
        error=None,
        clip_errors=None,
        debug_level=0,
        send_email=False,
    )
    html_body = send_mock.call_args.kwargs.get("html_body")
    assert html_body is not None
    assert 'width="64" height="64"' in html_body
