from extraction.quality import filter_rows, is_valid_ev_row


def test_rejects_bare_price_as_model():
    assert not is_valid_ev_row({"model": "16.19 - *", "ex_showroom_price": ""})
    assert not is_valid_ev_row({"model": "Under", "ex_showroom_price": "Rs. 8"})


def test_accepts_named_model_and_price():
    assert is_valid_ev_row(
        {"model": "Tata Nexon EV", "ex_showroom_price": "₹ 14.49 - 18.99 Lakh"}
    )


def test_filter_dedupes():
    rows = [
        {"model": "Tata Nexon EV", "ex_showroom_price": "₹ 14 Lakh"},
        {"model": "Tata Nexon EV", "ex_showroom_price": "₹ 14 Lakh"},
        {"model": "16.19", "ex_showroom_price": "x"},
    ]
    assert len(filter_rows(rows)) == 1
