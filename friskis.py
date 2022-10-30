import calendar
import json
import locale
from datetime import date, datetime, time, timedelta
from pathlib import Path

import click
import requests
from dateutil.parser import parse as fromisoformat
from pytz import timezone, utc

locale.setlocale(locale.LC_TIME, "sv_SE.UTF-8")

API_ENDPOINT = "https://friskissvettis.brpsystems.com/brponline/api/ver3"
BUSINESS_UNITS_URL = f"{API_ENDPOINT}/businessunits"
LOGIN_URL = f"{API_ENDPOINT}/auth/login"
PROJECT_ROOT = Path(__file__).parent
LOGIN_CREDENTIALS_PATH = PROJECT_ROOT / ".login.json"
SCHEDULE_PATH = PROJECT_ROOT / ".schedule.json"
STOCKHOLM_TIMEZONE = timezone("Europe/Stockholm")
WEEKDAYS = [day.lower() for day in calendar.day_name]


class FriskisException(Exception):
    pass

class Unauthorized(FriskisException):
    pass

class FriskisAPIError(FriskisException):
    pass


def _parse_datetime(s):
    return fromisoformat(s).astimezone(utc)


def _format_date(d):
    return d.isoformat()


def _format_datetime(dt, delimiter=" ", tz=STOCKHOLM_TIMEZONE, seconds=False):
    aware = dt.astimezone(tz)
    date_string = aware.date().isoformat()
    time_string = aware.strftime("%H:%M:%S" if seconds else "%H:%M")
    return f"{date_string}{delimiter}{time_string}"


def _format_name(name):
    return name.title()


def _format_location(location):
    return location.title()


def _pluralize_weekday(weekday):
    return f"{weekday}ar" if not weekday.endswith("ar") else weekday


def _format_weekday(weekday, plural=False):
    weekday = weekday.lower()
    return _pluralize_weekday(weekday) if plural else weekday


def _format_weekday_plural(weekday):
    return _format_weekday(weekday, plural=True)


def _get_formatted_arguments(name, location, weekday):
    return (
        _format_name(name),
        _format_location(location),
        _format_weekday_plural(weekday),
    )


def _strip_weekday_plural(ctx, weekday):
    if weekday is None:
        return None
    return weekday[:-2] if weekday.endswith("ar") else weekday


def _lowercase(ctx, s):
    if s is None:
        return None
    return s.lower()


def _normalize(ctx, s, formatters):
    if len(formatters) == 0:
        return s
    if len(formatters) == 1:
        return formatters[0](ctx, s)
    return _normalize(ctx, formatters[0](ctx, s), formatters[1:])


def _normalize_weekday(ctx, weekday):
    if weekday is None:
        return None
    return _normalize(ctx, weekday, [_lowercase, _strip_weekday_plural])


def _format_list_display(ctx, s):
    return _normalize(ctx, s, [lambda cty, v: v.ljust(16)])


def _get_weekday_number(weekday):
    return WEEKDAYS.index(weekday) + 1


def _get_weekday(weekday_number):
    return WEEKDAYS[weekday_number - 1]


def _get_business_units():
    business_units_response = requests.get(BUSINESS_UNITS_URL)
    if business_units_response.status_code != 200:
        raise click.ClickException(f"Det gick inte att hämta platser. ({business_units_response.status_code})")
    return business_units_response.json()


def _get_business_unit(name):
    business_units = _get_business_units()
    for business_unit in business_units:
        if business_unit["name"].lower() == name.lower():
            return business_unit

    existing = ', '.join(b['name'] for b in business_units)
    raise click.ClickException(f"Kunde inte hitta någon plats med det namnet. Hittade följande: {existing}")


def _get_group_activities(business_unit, day):
    url = f"{BUSINESS_UNITS_URL}/{business_unit['id']}/groupactivities"
    period_start = datetime.combine(day, time())
    period_end = period_start + timedelta(days=1)

    def datetime_to_string(dt):
        return _format_datetime(dt, delimiter="T", tz=utc, seconds=True) +".000Z"

    params = {
        "period.start": datetime_to_string(period_start),
        "period.end": datetime_to_string(period_end),
    }
    group_activities_response = requests.get(url, params)
    if group_activities_response.status_code != 200:
        raise click.ClickException("Det gick inte att hämta schemalagda aktiviteter.")
    return group_activities_response.json()


def _get_group_activity(name, day, business_unit):
    group_activities = _get_group_activities(business_unit, day)
    for group_activity in group_activities:
        if group_activity["name"].lower() == name.lower():
            return group_activity


def _get_upcoming_group_activity(name, location, weekday_number):
    today = datetime.now(STOCKHOLM_TIMEZONE).date()
    group_activity_date = today
    while group_activity_date.isoweekday() != weekday_number:
        group_activity_date += timedelta(days=1)
    business_unit = _get_business_unit(location)
    group_activity = _get_group_activity(name, group_activity_date, business_unit)
    return group_activity, group_activity_date


def _get_bookings(authorization):
    username = authorization["username"]
    url = f"{API_ENDPOINT}/customers/{username}/bookings/groupactivities"
    group_activities_response = _authorized_request(requests.get, url, authorization=authorization)
    if group_activities_response.status_code != 200:
        raise click.ClickException(f"Det gick inte att hämta befintliga bokningar. ({group_activities_response.status_code})")
    return group_activities_response.json()


def _get_login_credentials():
    with open(LOGIN_CREDENTIALS_PATH) as f:
        return json.load(f)


def _get_schedule():
    if not SCHEDULE_PATH.exists():
        return []
    with open(SCHEDULE_PATH) as f:
        return json.load(f)


def _set_schedule(schedule):
    with open(SCHEDULE_PATH, "w") as f:
        json.dump(schedule, f)


def _login():
    params = _get_login_credentials()
    login_response = requests.post(LOGIN_URL, json=params)
    if login_response.status_code == 200:
        return login_response.json()
    elif login_response.status_code == 401:
        raise click.ClickException("Det gick inte att logga in med angivna inloggningsuppgifter.")
    raise click.ClickException(f"Det gick inte att logga in. ({login_response.status_code})")


def _authorized_request(request_method, *request_args, authorization, **request_kwargs):
    token_type = authorization["token_type"]
    access_token = authorization["access_token"]
    headers = {
        **request_kwargs.pop("headers", {}),
        "authorization": f"{token_type} {access_token}",
    }
    return request_method(*request_args, **request_kwargs, headers=headers)


def _book_group_activity(group_activity, authorization):
    username = authorization["username"]
    url = f"{API_ENDPOINT}/customers/{username}/bookings/groupactivities"
    params = {
        "groupActivity": group_activity["id"],
        "allowWaitingList": False,
    }
    attend_group_activity_response = _authorized_request(requests.post, url, json=params, authorization=authorization)
    if attend_group_activity_response.status_code == 201:
        return attend_group_activity_response.json()
    return {}


@click.group()
def friskis():
    pass

@friskis.command("list")
@click.pass_context
def list_schedule(ctx):
    for event in sorted(_get_schedule(), key=lambda e: e["weekday"]):
        name = event["name"]
        weekday = _get_weekday(event["weekday"])
        click.echo(
            "\t\t".join(
                _format_list_display(ctx, column)
                for column in  [
                    name,
                    event["location"],
                    f"{weekday}ar".title(),
                ]
            )
        )


@friskis.command()
@click.argument("name", callback=_lowercase)
@click.argument("location", callback=_lowercase)
@click.argument("weekday", callback=_normalize_weekday)
def add(name, location, weekday):
    formatted_name, formatted_location, formatted_weekday = _get_formatted_arguments(name, location, weekday)
    schedule = _get_schedule()
    weekday_number = _get_weekday_number(weekday)
    for event in schedule:
        if name == event["name"] and location == event["location"] and weekday_number == event["weekday"]:
            raise click.ClickException(f"{formatted_name} på {formatted_location} på {formatted_weekday} finns redan i schemat.")

    group_activity, group_activity_date = _get_upcoming_group_activity(name, location, weekday_number)
    if not group_activity:
        formatted_group_activity_date = _format_date(group_activity_date)
        raise click.ClickException(f"{formatted_name} är inte schemalagt {formatted_group_activity_date} på {formatted_location}.")

    _set_schedule([*schedule, {"name": name, "location": location, "weekday": weekday_number}])

    if location is None:
        click.echo(f"Lade till {formatted_name} på {formatted_weekday} i schemat.")
    elif weekday is None:
        click.echo(f"Lade till {formatted_name} på {formatted_location} i schemat.")
    else:
        click.echo(f"Lade till {formatted_name} på {formatted_location} på {formatted_weekday} i schemat.")


@friskis.command()
@click.argument("name", callback=_lowercase)
@click.argument("location", required=False, callback=_lowercase)
@click.argument("weekday", required=False, callback=_normalize_weekday)
def remove(name, location=None, weekday=None):
    formatted_name, formatted_location, formatted_weekday = _get_formatted_arguments(name, location, weekday)
    schedule = _get_schedule()
    weekday_number = _get_weekday_number(weekday) if weekday else None
    matches = []
    for event in schedule:
        if (
            name.lower() in event["name"].lower() and
            location is not None and location.lower() == event["location"].lower() and
            weekday is not None and weekday_number == event["weekday"]
        ):
            matches.append(event)
            if len(matches) > 1:
                if location is None:
                    raise click.ClickException(f"{name} på {weekday} matchade flera gånger i schemat. Prova att ange plats.")
                elif weekday is None:
                    raise click.ClickException(f"{name} på {location} matchade flera gånger i schemat. Prova att ange veckodag.")
                else:
                    raise click.ClickException(f"{name} matchade flera gånger i schemat. Prova att ange plats och/eller veckodag.")

    if len(matches) == 0:
        if location is None and weekday is None:
            raise click.ClickException(f"{name} matchade inte något i schemat.")
        elif weekday is None:
            raise click.ClickException(f"{name} och {location} matchade inte något i schemat.")
        elif location is None:
            raise click.ClickException(f"{name} och {weekday} matchade inte något i schemat.")
        else:
            raise click.ClickException(f"{name}, {location} och {weekday} matchade inte något i schemat.")

    _set_schedule([e for e in schedule if e not in matches])

    if location is None:
        click.echo(f"Tog bort {formatted_name} på {formatted_weekday} ur schemat.")
    elif weekday is None:
        click.echo(f"Tog bort {formatted_name} på {formatted_location} ur schemat.")
    else:
        click.echo(f"Tog bort {formatted_name} på {formatted_location} på {formatted_weekday} ur schemat.")


@friskis.command()
def book():
    now = datetime.now(STOCKHOLM_TIMEZONE)
    authorization = _login()
    existing_bookings = _get_bookings(authorization)
    for event in _get_schedule():
        group_activity_name = event["name"]
        group_activity_weekday = event["weekday"]
        location = event["location"]
        formatted_name, formatted_location = _format_name(group_activity_name), _format_location(location)

        group_activity, group_activity_date = _get_upcoming_group_activity(group_activity_name, location, group_activity_weekday)
        formatted_group_activity_date = group_activity_date.isoformat()
        if not group_activity:
            click.echo(f"{formatted_name} är inte schemalagt på {formatted_location} {formatted_group_activity_date}.")
            continue
        if group_activity["cancelled"]:
            click.echo(f"{formatted_name} på {formatted_location} är inställt {formatted_group_activity_date}")

        bookable_earliest = _parse_datetime(group_activity["bookableEarliest"])
        already_booked = group_activity["id"] in [booking["groupActivity"]["id"] for booking in existing_bookings]
        if now < bookable_earliest or already_booked:
            continue

        slots = group_activity["slots"]
        slots_left = slots["leftToBook"]
        if slots_left == 0:
            waiting_list_length = slots["inWaitingList"]
            click.echo(
                f"{formatted_name} på {formatted_location} {formatted_group_activity_date} är fullbokat. "
                f"Det är {waiting_list_length} {'personer' if waiting_list_length > 1 else 'person'} på reservplats."
            )
            continue

        group_activity_booking = _book_group_activity(group_activity, authorization)
        if not group_activity_booking:
            continue

        group_activity_booking_start = _parse_datetime(group_activity_booking["duration"]["start"])

        click.echo(f"{formatted_name} på {formatted_location} {_format_datetime(group_activity_booking_start)} bokades!")


if __name__ == '__main__':
    friskis()
