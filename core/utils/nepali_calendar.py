from datetime import date, datetime, time

from django.conf import settings

try:
    import nepali_datetime
except ImportError:
    nepali_datetime = None


def ad_to_bs(ad_date):
    if not ad_date:
        return ''
    if nepali_datetime is None:
        return ad_date.strftime('%Y-%m-%d')
    try:
        if isinstance(ad_date, datetime):
            bs = nepali_datetime.date.from_datetime_date(ad_date.date())
        else:
            bs = nepali_datetime.date.from_datetime_date(ad_date)
        return bs.strftime('%Y-%m-%d')
    except Exception:
        return ad_date.strftime('%Y-%m-%d')


def bs_to_ad(bs_str):
    if not bs_str or nepali_datetime is None:
        return None
    try:
        parts = bs_str.strip().split('-')
        if len(parts) != 3:
            return None
        bs_date = nepali_datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
        ad = bs_date.to_datetime_date()
        return ad
    except Exception:
        return None


def current_bs_date():
    if nepali_datetime is None:
        return date.today().strftime('%Y-%m-%d')
    try:
        return nepali_datetime.date.today().strftime('%Y-%m-%d')
    except Exception:
        return date.today().strftime('%Y-%m-%d')


def ad_to_bs_datetime_string(ad_datetime):
    if not ad_datetime:
        return ''
    if nepali_datetime is None:
        return ad_datetime.strftime('%Y-%m-%d %H:%M:%S')
    try:
        if isinstance(ad_datetime, datetime):
            bs = nepali_datetime.datetime.from_datetime(ad_datetime)
        else:
            bs = nepali_datetime.datetime.from_datetime(datetime.combine(ad_datetime, time.min))
        return bs.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return ad_datetime.strftime('%Y-%m-%d %H:%M:%S')
