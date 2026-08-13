from datetime import date

from proof.day_zero_20 import values_match


TODAY = date(2026, 8, 12)


def differences(field, actual):
    return values_match({"fields": [field]}, {field["name"]: actual}, today=TODAY)


def test_oracle_accepts_only_semantically_equal_native_dates():
    field = {"name": "day", "kind": "text", "value": "tomorrow"}
    assert differences(field, "2026-08-13") == []
    assert differences(field, "2026-08-14")


def test_oracle_normalizes_weekdays_and_month_dates():
    assert differences({"name": "day", "kind": "text", "value": "Friday"},
                       "2026-08-14") == []
    assert differences({"name": "day", "kind": "text", "value": "August 18"},
                       "2026-08-18") == []


def test_oracle_accepts_equivalent_12_and_24_hour_times_only():
    field = {"name": "time", "kind": "text", "value": "10:30 AM"}
    assert differences(field, "10:30") == []
    assert differences(field, "22:30")


def test_oracle_keeps_nonsemantic_text_strict():
    field = {"name": "venue", "kind": "text", "value": "Cedar House"}
    assert differences(field, "Cedar House") == []
    assert differences(field, "Cedar House Downtown")


def test_oracle_accepts_only_empty_ui_wording_around_an_outcome():
    field = {"name": "resolution", "kind": "text", "value": "Corrected bill"}
    assert differences(field, "request a corrected bill") == []
    assert differences(field, "do not request a corrected bill")
    assert differences(field, "request a corrected bill and refund")


def test_oracle_accepts_field_label_echo_but_not_an_unrelated_extra():
    field = {"name": "trip", "label": "Trip", "kind": "text",
             "value": "Science Centre"}
    assert differences(field, "Science Centre trip") == []
    assert differences(field, "Science Centre aquarium")


def test_problem_state_verb_can_be_omitted_without_changing_the_problem():
    field = {"name": "problem", "label": "Problem", "kind": "text",
             "value": "Arrived damaged"}
    assert differences(field, "damaged") == []
    assert differences(field, "lost")


def test_service_method_may_omit_the_redundant_repair_noun():
    field = {"name": "service", "label": "Service method", "kind": "text",
             "value": "Mail-in repair"}
    assert differences(field, "mail-in") == []
    assert differences(field, "on-site")


def test_free_text_may_repeat_other_form_values_but_not_add_an_outcome():
    case = {"fields": [
        {"name": "invoice", "value": "INV-52192", "kind": "text"},
        {"name": "po", "value": "PO-3439", "kind": "text"},
        {"name": "agreed", "value": "1947.00", "kind": "text"},
        {"name": "resolution", "label": "Requested resolution",
         "value": "Corrected invoice", "kind": "text"},
    ]}
    actual = {"invoice": "INV-52192", "po": "PO-3439", "agreed": "1947.00",
              "resolution": "Request corrected invoice for INV-52192 against PO-3439 for $1947.00"}
    assert values_match(case, actual, today=TODAY) == []
    actual["resolution"] += " and refund"
    assert values_match(case, actual, today=TODAY)
