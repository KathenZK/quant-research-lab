"""Root-selected UTC continuous calendar month turn; no price-derived indicator."""
from calendar import monthrange
from datetime import datetime, timezone

DAY = 86400000

def features(rows):
    output = []
    for i, row in enumerate(rows):
        ms = int(row['open_time'])
        assert ms % DAY == 0, 'Daily open must be UTC midnight'
        assert int(row['close_time']) == ms + DAY - 1
        date = datetime.fromtimestamp(ms // 1000, timezone.utc).date()
        length = monthrange(date.year, date.month)[1]
        output.append(dict(input_index=i, open_time=row['open_time'], close_time=row['close_time'],
                           close=row['close'], utc_date=date.isoformat(), days_in_month=length,
                           ready=1, raw_entry=int(date.day == length - 2), raw_exit=int(date.day == 3)))
    return output
