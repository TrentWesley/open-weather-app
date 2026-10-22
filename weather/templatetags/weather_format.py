"""Template filters for dashboard values; see weather.formatting.

The time filters format in the datetime's own zone. Django's `date` filter would
convert to the server's TIME_ZONE instead of the location's local time.
"""
from datetime import datetime

from django import template

from weather import formatting

register = template.Library()

register.filter("temperature", formatting.format_temperature)
register.filter("speed", formatting.format_speed)
register.filter("distance", formatting.format_distance)
register.filter("local_time", formatting.format_time, expects_localtime=False)
register.filter("local_datetime", formatting.format_datetime, expects_localtime=False)
register.filter("hour_label", formatting.format_hour, expects_localtime=False)
register.filter("day_label", formatting.format_date)
register.filter("percent", formatting.format_percent)
register.filter("precipitation", formatting.format_precipitation)
register.filter("age", formatting.format_age)
register.filter("icon_url", formatting.icon_url)


@register.filter(expects_localtime=False)
def in_zone_of(moment: datetime, reference: datetime) -> datetime:
    """Express `moment` in the zone of `reference`, e.g. UTC fetch time in local time."""
    return moment.astimezone(reference.tzinfo)


@register.filter
def place_name(location) -> str:
    """"Name, State, Country", skipping parts the API didn't provide."""
    return ", ".join(part for part in (location.name, location.state, location.country) if part)
