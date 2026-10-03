"""Independent ordinal/next-month subtraction calendar; no monthrange or adapter import."""
from datetime import date

DAY = 86400000
EPOCH_ORDINAL = date(1970, 1, 1).toordinal()

def expected_features(rows):
    output = []
    for row in rows:
        ms = int(row['open_time'])
        assert ms % DAY == 0 and int(row['close_time']) == ms + DAY - 1
        day = date.fromordinal(EPOCH_ORDINAL + ms // DAY)
        next_month = date(day.year + (day.month == 12), day.month % 12 + 1, 1)
        length = (next_month - date(day.year, day.month, 1)).days
        output.append(dict(utc_date=day.isoformat(), days_in_month=length, ready=True,
                           entry=(next_month - day).days == 3, exit=day.day == 3))
    return output

def verify_features(rows, actual):
    expected = expected_features(rows)
    assert len(actual) == len(rows)
    for i, (saved, want, row) in enumerate(zip(actual, expected, rows)):
        assert int(saved['input_index']) == i
        for field in ['open_time', 'close_time', 'close']:
            assert saved[field] == row[field]
        for field in ['utc_date', 'days_in_month', 'ready']:
            assert str(saved[field]) == str(int(want[field]) if isinstance(want[field], bool) else want[field])
        assert int(saved['raw_entry']) == want['entry'] and int(saved['raw_exit']) == want['exit']
    return expected
