import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from bus_times import (
    minutes_until,
    get_color_for_minutes,
    get_next_buses,
    parse_html,
    get_next_bus,
)


class TestMinutesUntil:
    def test_minutes_until_future_time(self):
        future_time = (datetime.now() + timedelta(minutes=30)).strftime("%H:%M")
        result = minutes_until(future_time)
        assert result is not None
        assert 29 <= result <= 30

    def test_minutes_until_past_time_today(self):
        past_time = (datetime.now() - timedelta(minutes=5)).strftime("%H:%M")
        result = minutes_until(past_time)
        assert result == 0

    def test_minutes_until_invalid_format(self):
        result = minutes_until("invalid")
        assert result is None

    def test_minutes_until_current_time(self):
        current_time = datetime.now().strftime("%H:%M")
        result = minutes_until(current_time)
        assert result == 0


class TestGetColorForMinutes:
    def test_red_under_5_minutes(self):
        assert get_color_for_minutes(1) == (255, 0, 0)
        assert get_color_for_minutes(4) == (255, 0, 0)

    def test_orange_5_to_15_minutes(self):
        assert get_color_for_minutes(5) == (255, 165, 0)
        assert get_color_for_minutes(10) == (255, 165, 0)
        assert get_color_for_minutes(15) == (255, 165, 0)

    def test_green_over_15_minutes(self):
        assert get_color_for_minutes(16) == (0, 255, 0)
        assert get_color_for_minutes(30) == (0, 255, 0)


class TestGetNextBuses:
    @patch('bus_times.MIN_MINUTES', 3)
    def test_filters_buses_under_min_minutes(self):
        departures = [
            {"line": "1", "destination": "A", "scheduled": "10:00", "expected": "10:02"},
            {"line": "2", "destination": "B", "scheduled": "10:10", "expected": "10:10"},
        ]
        now = datetime.now().replace(hour=10, minute=0)
        with patch('bus_times.datetime', now=now):
            with patch('bus_times.minutes_until') as mock_mins:
                mock_mins.side_effect = lambda t: {
                    "10:02": 2,
                    "10:10": 10,
                }.get(t)
                result = get_next_buses(departures, 4)
                assert len(result) == 1
                assert result[0]["line"] == "2"

    def test_returns_empty_for_no_departures(self):
        result = get_next_buses([], 4)
        assert result == []

    def test_sorts_by_minutes(self):
        departures = [
            {"line": "1", "destination": "A", "scheduled": "10:30", "expected": "10:30"},
            {"line": "2", "destination": "B", "scheduled": "10:10", "expected": "10:10"},
        ]
        now = datetime.now().replace(hour=10, minute=0)
        with patch('bus_times.datetime', now=now):
            with patch('bus_times.minutes_until') as mock_mins:
                mock_mins.side_effect = lambda t: {
                    "10:30": 30,
                    "10:10": 10,
                }.get(t)
                result = get_next_buses(departures, 4)
                assert len(result) == 2
                assert result[0]["line"] == "2"
                assert result[1]["line"] == "1"


class TestGetNextBus:
    def test_returns_first_upcoming_bus(self):
        departures = [
            {"line": "1", "destination": "A", "scheduled": "10:00", "expected": "10:00"},
            {"line": "2", "destination": "B", "scheduled": "10:15", "expected": "10:15"},
        ]
        with patch('bus_times.minutes_until') as mock_mins:
            mock_mins.side_effect = lambda t: {
                "10:00": 0,
                "10:15": 15,
            }.get(t)
            result = get_next_bus(departures)
            assert result["line"] == "2"

    def test_returns_none_for_empty_departures(self):
        result = get_next_bus([])
        assert result is None


class TestParseHtml:
    def test_parses_valid_html(self):
        html = '''
        <html>
            <body>
                <div id="departures">
                    <table>
                        <tbody>
                            <tr>
                                <td><a>1</a></td>
                                <td>Destination A</td>
                                <td>10:00</td>
                                <td><a>10:05</a></td>
                            </tr>
                            <tr>
                                <td><a>2</a></td>
                                <td>Destination B</td>
                                <td>10:10</td>
                                <td></td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </body>
        </html>
        '''
        result = parse_html(html)
        assert len(result) == 2
        assert result[0]["line"] == "1"
        assert result[0]["destination"] == "Destination A"
        assert result[0]["scheduled"] == "10:00"
        assert result[0]["expected"] == "10:05"
        assert result[1]["line"] == "2"
        assert result[1]["expected"] == "10:10"

    def test_returns_empty_for_no_departures_div(self):
        html = '<html><body><div id="other"></div></body></html>'
        result = parse_html(html)
        assert result == []

    def test_returns_empty_for_no_table(self):
        html = '<html><body><div id="departures"></div></body></html>'
        result = parse_html(html)
        assert result == []
