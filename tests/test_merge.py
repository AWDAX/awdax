from extraction.merge import merge_tables
from extraction.models import ExtractedTable


def test_merge_aligns_columns_and_adds_source():
    t1 = ExtractedTable(
        name="A",
        source_url="https://www.cardekho.com/electric-cars",
        columns=["model", "ex_showroom_price"],
        rows=[["Nexon EV", "14 Lakh"]],
        row_count=1,
    )
    t2 = ExtractedTable(
        name="B",
        source_url="https://www.carwale.com/electric-cars",
        columns=["model", "ex_showroom_price"],
        rows=[["Punch EV", "9 Lakh"]],
        row_count=1,
    )
    master = merge_tables([t1, t2])
    assert master is not None
    assert master.row_count == 2
    assert master.columns[0] == "S. No."
    assert master.columns[1] == "source"
    assert master.rows[0][0] == "1"
    assert "cardekho.com" in master.rows[0][1]
    assert master.rows[0][3] == "Nexon EV"


def test_upsert_appends_new_rows():
    from extraction.merge import merge_tables, upsert_master_table

    t1 = ExtractedTable(
        name="a",
        source_url="https://cardekho.com/x",
        columns=["brand", "model", "ex_showroom_price"],
        rows=[["Tata", "Nexon EV", "14 Lakh"]],
        row_count=1,
    )
    master = merge_tables([t1])
    t2 = ExtractedTable(
        name="a",
        source_url="https://cardekho.com/x",
        columns=["brand", "model", "ex_showroom_price"],
        rows=[
            ["Tata", "Nexon EV", "14.5 Lakh"],
            ["MG", "Comet", "7.9 Lakh"],
        ],
        row_count=2,
    )
    fresh = merge_tables([t2])
    merged, added = upsert_master_table(master, fresh)
    assert merged.row_count == 2
    assert added == 1
