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
    body = "\n".join(send_mock.call_args.args[3])
    for offer in offers:
        assert str(offer) in body
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
    body = "\n".join(send_mock.call_args.args[3])
    assert str(free_one) in body
    assert str(free_two) in body
    assert str(not_free) not in body
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
    body = "\n".join(send_mock.call_args.args[3])
    assert str(offer) in body


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
    body = "\n".join(send_mock.call_args.args[3])
    assert str(offer) not in body


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
