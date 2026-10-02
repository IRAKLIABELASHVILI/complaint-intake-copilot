"""Personal data redaction (US-6). One test per data type, each with "should NOT redact" cases."""

import pytest

from app.domain.redaction import RedactedText, RedactionError, redact


def r(text: str, sender_name: str | None = None) -> str:
    return redact(text, sender_name=sender_name).value


# --- Email ---------------------------------------------------------------------------------------


def test_email_addresses_are_redacted() -> None:
    assert r("Write to jane.doe+bank@example.co.uk today") == "Write to [EMAIL_1] today"


def test_the_same_email_gets_the_same_placeholder() -> None:
    text = "a@x.com, b@x.com, then A@X.COM again"

    assert r(text) == "[EMAIL_1], [EMAIL_2], then [EMAIL_1] again"


def test_an_at_sign_without_a_domain_is_not_an_email() -> None:
    assert r("Meet @ 5pm at the branch") == "Meet @ 5pm at the branch"


# --- Card numbers (13-19 digits, Luhn) -----------------------------------------------------------


@pytest.mark.parametrize(
    "card", ["4111 1111 1111 1111", "4111-1111-1111-1111", "4111111111111111", "378282246310005"]
)
def test_card_numbers_that_pass_luhn_are_redacted(card: str) -> None:
    assert r(f"Card {card} was charged") == "Card [CARD_1] was charged"


def test_a_long_number_that_fails_luhn_is_not_a_card() -> None:
    assert r("Reference 4111 1111 1111 1112 on my letter") == (
        "Reference 4111 1111 1111 1112 on my letter"
    )


def test_the_same_card_written_two_ways_is_one_placeholder() -> None:
    assert r("4111 1111 1111 1111 and 4111-1111-1111-1111") == "[CARD_1] and [CARD_1]"


# --- Sort codes and account numbers --------------------------------------------------------------


def test_sort_codes_are_redacted() -> None:
    assert r("sort code 20-45-67, please") == "sort code [SORT_CODE_1], please"


def test_a_date_is_not_a_sort_code() -> None:
    assert r("On 12-03-2026 I called") == "On 12-03-2026 I called"


def test_eight_digit_account_numbers_are_redacted() -> None:
    assert r("Account number 12345678.") == "Account number [ACCOUNT_1]."


@pytest.mark.parametrize(
    "text",
    [
        "I was charged £1,250.00 in total",
        "I was charged £12345678",
        "Reference 123456789 is nine digits",
        "Only 1234567 seven digits",
        "Version 1.12345678",
    ],
)
def test_amounts_and_other_numbers_are_not_account_numbers(text: str) -> None:
    assert r(text) == text


# --- UK phone numbers ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phone",
    [
        "07700 900123",
        "07700900123",
        "+44 7700 900123",
        "+447700900123",
        "+44 (0)7700 900123",
        "020 7946 0958",
        "0161 496 0000",
        "01632 960123",
        "0300 123 4567",
    ],
)
def test_uk_phone_numbers_are_redacted(phone: str) -> None:
    assert r(f"Call me on {phone} today") == "Call me on [PHONE_1] today"


def test_the_same_phone_with_and_without_country_code_is_one_placeholder() -> None:
    assert r("07700 900123 or +44 7700 900123") == "[PHONE_1] or [PHONE_1]"


@pytest.mark.parametrize("text", ["Case 0800 is open", "Ref 0123 456 only", "0900 hours"])
def test_short_or_non_uk_numbers_are_not_phone_numbers(text: str) -> None:
    assert r(text) == text


# --- Postcodes -----------------------------------------------------------------------------------


@pytest.mark.parametrize("postcode", ["SW1A 1AA", "M1 1AE", "B33 8TH", "CR2 6XH", "EC1A 1BB"])
def test_uk_postcodes_are_redacted(postcode: str) -> None:
    assert r(f"I live at {postcode} now") == "I live at [POSTCODE_1] now"


def test_lower_case_postcodes_are_redacted_too() -> None:
    assert r("send it to sw1a 1aa") == "send it to [POSTCODE_1]"


@pytest.mark.parametrize("text", ["I paid on the 3rd", "Flight BA2490 was late", "Form P60 lost"])
def test_ordinary_words_and_codes_are_not_postcodes(text: str) -> None:
    assert r(text) == text


# --- Names ---------------------------------------------------------------------------------------


def test_the_senders_name_and_its_parts_are_redacted() -> None:
    text = "Margaret Ellison here. Margaret is my first name.\n\nRegards,\nMargaret Ellison"

    assert r(text, sender_name="Margaret Ellison") == (
        "[NAME_1] here. [NAME_1] is my first name.\n\nRegards,\n[NAME_1]"
    )


def test_names_after_greetings_and_sign_offs_are_redacted() -> None:
    text = "Dear Mr Patel,\nPlease help.\nKind regards, Sophie Turner"

    assert r(text) == "Dear Mr [NAME_1],\nPlease help.\nKind regards, [NAME_2]"


def test_greetings_to_no_one_in_particular_are_kept() -> None:
    assert r("Dear Sir or Madam,\nHello team,") == "Dear Sir or Madam,\nHello team,"


def test_a_name_that_is_also_a_word_is_only_redacted_when_capitalised() -> None:
    assert r("Will Smith says: I will call.", sender_name="Will Smith") == (
        "[NAME_1] says: I will call."
    )


@pytest.mark.parametrize(
    "name", ["Sean O'Brien", "Sean O" + chr(0x2019) + "Brien", "Ian McDonald", "Ana Smith-Jones"]
)
def test_names_with_apostrophes_capitals_and_hyphens_are_redacted(name: str) -> None:
    assert r("Regards, " + name) == "Regards, [NAME_1]"
    assert r(f"Thanks, {name}", sender_name=name) == "Thanks, [NAME_1]"


def test_capitals_only_words_after_a_greeting_are_not_names() -> None:
    assert r("Hello NHS team") == "Hello NHS team"


def test_thank_you_in_a_sentence_is_not_a_sign_off() -> None:
    assert r("Thank you for nothing so far.") == "Thank you for nothing so far."


# --- The whole complaint -------------------------------------------------------------------------


def test_a_realistic_complaint_keeps_its_meaning_and_loses_its_personal_data() -> None:
    text = (
        "Dear Sir or Madam,\n\n"
        "My card 4111 1111 1111 1111 was charged £35 on 12-03-2026. "
        "Account 12345678, sort code 20-45-67. Call 07700 900123 or email m.e@example.com. "
        "I live at SW1A 1AA.\n\nRegards,\nMargaret Ellison"
    )

    redacted = redact(text, sender_name="Margaret Ellison")

    assert redacted.value == (
        "Dear Sir or Madam,\n\n"
        "My card [CARD_1] was charged £35 on 12-03-2026. "
        "Account [ACCOUNT_1], sort code [SORT_CODE_1]. Call [PHONE_1] or email [EMAIL_1]. "
        "I live at [POSTCODE_1].\n\nRegards,\n[NAME_1]"
    )
    assert dict(redacted.counts) == {
        "EMAIL": 1,
        "CARD": 1,
        "SORT_CODE": 1,
        "PHONE": 1,
        "ACCOUNT": 1,
        "POSTCODE": 1,
        "NAME": 1,
    }


def test_text_without_personal_data_is_unchanged() -> None:
    text = "The app crashed twice and I was charged £3.50 for nothing."

    assert redact(text) == RedactedText(text, redact(text).counts)
    assert dict(redact(text).counts) == {}


def test_truncation_keeps_the_counts() -> None:
    redacted = redact("Email a@b.com please")

    assert redacted.truncated(5).value == "Email"
    assert redacted.truncated(5).counts == redacted.counts


def test_an_unexpected_failure_is_reported_as_a_redaction_error() -> None:
    with pytest.raises(RedactionError):
        redact(None)  # type: ignore[arg-type]
