import unittest
from datetime import date

from scripts.historical_backtest import parse_end_date


class HistoricalBacktestDateTests(unittest.TestCase):
    def test_range_with_year_does_not_use_year_as_day(self):
        self.assertEqual(
            parse_end_date("24–26 Sep 2018", 2018),
            date(2018, 9, 26),
        )

    def test_range_crossing_month(self):
        self.assertEqual(
            parse_end_date("28 Sep – 2 Oct 2018", 2018),
            date(2018, 10, 2),
        )

    def test_single_date_with_full_month_name(self):
        self.assertEqual(
            parse_end_date("6 October 2018", 2018),
            date(2018, 10, 6),
        )

    def test_yearless_range_uses_study_year(self):
        self.assertEqual(
            parse_end_date("29 Sep - 1 Oct", 2022),
            date(2022, 10, 1),
        )


if __name__ == "__main__":
    unittest.main()
