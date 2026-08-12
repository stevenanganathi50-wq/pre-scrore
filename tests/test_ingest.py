"""Parsing tests for the football-data.co.uk CSV format."""

import unittest

from prescore.ingest import football_data as fd

CSV = """Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,AvgCH,AvgCD,AvgCA
E0,16/08/2024,20:00,Man United,Fulham,1,0,H,1.85,3.60,4.40
E0,17/08/2024,12:30,Ipswich,Liverpool,0,2,A,7.50,4.80,1.44
E0,17/08/2024,15:00,Arsenal,Wolves,2,0,H,1.30,6.00,10.0
"""


def parse(text, div=None):
    """parse_season without the wrong-division counter, for brevity."""
    matches, _ = fd.parse_season(text, div=div)
    return matches


class TestSeasonCodes(unittest.TestCase):
    def test_season_code(self):
        self.assertEqual(fd.season_code(2015), "1516")
        self.assertEqual(fd.season_code(2024), "2425")
        self.assertEqual(fd.season_code(2026), "2627")

    def test_url_shape(self):
        self.assertEqual(
            fd.csv_url(2024, "E0"),
            "https://www.football-data.co.uk/mmz4281/2425/E0.csv",
        )


class TestParseSeason(unittest.TestCase):
    def test_parses_every_valid_row(self):
        matches = parse(CSV)
        self.assertEqual(len(matches), 3)

    def test_normalizes_fields(self):
        first = parse(CSV)[0]
        self.assertEqual(first["date"], "2024-08-16")
        self.assertEqual(first["time"], "20:00")
        self.assertEqual(first["home"], "Man United")
        self.assertEqual(first["home_goals"], 1)
        self.assertEqual(first["result"], "H")
        self.assertEqual(first["odds"], (1.85, 3.60, 4.40))

    def test_handles_two_digit_years(self):
        csv = CSV.replace("16/08/2024", "16/08/24")
        self.assertEqual(parse(csv)[0]["date"], "2024-08-16")

    def test_skips_rows_without_a_result(self):
        csv = CSV + "E0,24/08/2024,15:00,Chelsea,Everton,,,,,,\n"
        self.assertEqual(len(parse(csv)), 3)

    def test_skips_blank_trailing_rows(self):
        csv = CSV + ",,,,,,,,,,\n\n"
        self.assertEqual(len(parse(csv)), 3)

    def test_derives_result_when_column_is_missing(self):
        csv = CSV.replace(",H,1.85", ",,1.85")
        self.assertEqual(parse(csv)[0]["result"], "H")

    def test_falls_back_through_odds_columns(self):
        csv = CSV.replace("AvgCH,AvgCD,AvgCA", "B365H,B365D,B365A")
        self.assertEqual(parse(csv)[0]["odds"], (1.85, 3.60, 4.40))

    def test_missing_odds_become_none(self):
        csv = "\n".join(
            line.rsplit(",", 3)[0] for line in CSV.strip().splitlines()
        )
        self.assertEqual(parse(csv)[0]["odds"], (None, None, None))


class TestDivisionFilter(unittest.TestCase):
    """Regression: the published 2026/27 E0.csv was seeded with National
    League (Div=EC) rows, which created phantom Premier League teams."""

    OTHER_DIVISION = (
        "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"
        "EC,08/08/2026,15:00,Hornchurch,Kidderminster,3,0,H\n"
        "EC,08/08/2026,15:00,Woking,Sutton,0,3,A\n"
    )

    def test_rows_from_another_division_are_dropped(self):
        matches, wrong = fd.parse_season(self.OTHER_DIVISION, div="E0")
        self.assertEqual(matches, [])
        self.assertEqual(wrong, 2)

    def test_matching_division_is_kept(self):
        matches, wrong = fd.parse_season(CSV, div="E0")
        self.assertEqual(len(matches), 3)
        self.assertEqual(wrong, 0)

    def test_mixed_file_keeps_only_the_requested_division(self):
        mixed = CSV + "EC,18/08/2024,15:00,Woking,Sutton,0,3,A,2.0,3.5,3.7\n"
        matches, wrong = fd.parse_season(mixed, div="E0")
        self.assertEqual(len(matches), 3)
        self.assertEqual(wrong, 1)
        self.assertNotIn("Woking", [m["home"] for m in matches])

    def test_omitting_the_filter_accepts_everything(self):
        matches, wrong = fd.parse_season(self.OTHER_DIVISION)
        self.assertEqual(len(matches), 2)
        self.assertEqual(wrong, 0)

    def test_division_comparison_is_case_insensitive(self):
        matches, _ = fd.parse_season(CSV, div="e0")
        self.assertEqual(len(matches), 3)


class TestBom(unittest.TestCase):
    def test_leading_bom_does_not_break_the_header(self):
        matches = parse("﻿" + CSV)
        self.assertEqual(len(matches), 3)


if __name__ == "__main__":
    unittest.main()
