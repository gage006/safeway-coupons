import pytest_mock

from safeway_coupons import email as email_mod
from safeway_coupons.email import email_clip_results

from .utils import create_account, create_offer


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


def test_html_uses_cid_when_images_provided(
    mocker: pytest_mock.MockerFixture,
) -> None:
    send_mock = mocker.patch.object(email_mod, "_send_email")
    offer = create_offer("42", offer_price="$2 OFF")
    img_bytes = b"GIF89afake"
    email_clip_results(
        sendmail=["/usr/sbin/sendmail"],
        account=create_account(),
        offers=[offer],
        error=None,
        clip_errors=None,
        debug_level=0,
        send_email=False,
        offer_images={"42": img_bytes},
    )
    html_body = send_mock.call_args.kwargs.get("html_body")
    assert html_body is not None
    assert "cid:42" in html_body
    assert send_mock.call_args.kwargs.get("offer_images") == {"42": img_bytes}


def test_html_falls_back_to_url_without_images(
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
    assert "cid:42" not in html_body
    assert offer.image in html_body


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
