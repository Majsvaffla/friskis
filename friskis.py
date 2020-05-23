import calendar
import json
import locale
from datetime import date, datetime, timedelta, time
from pathlib import Path

import click
import requests
from dateutil.parser import parse as fromisoformat
from pytz import timezone, utc

locale.setlocale(locale.LC_TIME, "sv_SE.UTF-8")

API_ENDPOINT = "https://bokning.linkoping.friskissvettis.se/brponline/api/ver3"
BUSINESS_UNITS_URL = f"{API_ENDPOINT}/businessunits"
LOGIN_URL = f"{API_ENDPOINT}/auth/login"
PROJECT_ROOT = Path(__file__).parent
LOGIN_CREDENTIALS_PATH = PROJECT_ROOT / ".login"
SCHEDULE_PATH = PROJECT_ROOT / ".schedule"
STOCKHOLM_TIMEZONE = timezone("Europe/Stockholm")
WEEKDAYS = list(calendar.day_name)


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
    for business_unit in _get_business_units():
        if business_unit["name"].lower() == name.lower():
            return business_unit


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
        raise click.ClickException(f"Det gick inte att hämta befintilga bokningar. ({group_activities_response.status_code})")
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

@friskis.command()
def list():
    for event in sorted(_get_schedule(), key=lambda e: e["weekday"]):
        name = event["name"]
        weekday = _get_weekday(event["weekday"])
        click.echo("\t".join([name, event["location"], f"{weekday}ar".title()]))


@friskis.command()
@click.argument("name")
@click.argument("location")
@click.argument("weekday")
def add(name, location, weekday):
    schedule = _get_schedule()
    weekday_number = _get_weekday_number(weekday)
    for event in schedule:
        if name == event["name"] and location == event["location"] and weekday_number == event["weekday"]:
            raise click.ClickException(f"{name} på {location} på {weekday}ar finns redan i schemat.")

    group_activity, group_activity_date = _get_upcoming_group_activity(name, location, weekday_number)
    if not group_activity:
        formatted_group_activity_date = _format_date(group_activity_date)
        raise click.ClickException(f"{name} är inte schemalagt {formatted_group_activity_date} på {location}.")

    _set_schedule([*schedule, {"name": name, "location": location, "weekday": weekday_number}])

    if location is None:
        click.echo(f"Lade till {name} på {weekday}ar i schemat.")
    elif weekday is None:
        click.echo(f"Lade till {name} på {location} i schemat.")
    else:
        click.echo(f"Lade till {name} på {location} på {weekday}ar i schemat.")


@friskis.command()
@click.argument("name")
@click.argument("location", required=False)
@click.argument("weekday", required=False)
def remove(name, location=None, weekday=None):
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
                    raise click.ClickException(f"{name} på {weekday}ar matchade flera gånger i schemat. Prova att ange plats.")
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
            raise click.ClickException(f"{name} och {weekday}ar matchade inte något i schemat.")
        else:
            raise click.ClickException(f"{name}, {location} och {weekday}ar matchade inte något i schemat.")

    _set_schedule([e for e in schedule if e not in matches])

    if location is None:
        click.echo(f"Tog bort {name} på {weekday}ar ur schemat.")
    elif weekday is None:
        click.echo(f"Tog bort {name} på {location} ur schemat.")
    else:
        click.echo(f"Tog bort {name} på {location} på {weekday}ar ur schemat.")


@friskis.command()
def book():
    authorization = _login()
    existing_bookings = _get_bookings(authorization)
    for event in _get_schedule():
        group_activity_name = event["name"]
        group_activity_weekday = event["weekday"]
        location = event["location"]

        group_activity, group_activity_date = _get_upcoming_group_activity(group_activity_name, location, group_activity_weekday)
        formatted_group_activity_date = group_activity_date.isoformat()
        if not group_activity:
            click.echo(f"{group_activity_name} är inte schemalagt på {location} {formatted_group_activity_date}.")
            continue
        if group_activity["cancelled"]:
            click.echo(f"{group_activity_name} på {location} är inställt {formatted_group_activity_date}")

        bookable_earliest = _parse_datetime(group_activity["bookableEarliest"])
        already_booked = group_activity in [booking["groupActivity"] for booking in existing_bookings]
        if now < bookable_earliest or already_booked:
            continue

        slots = group_activity["slots"]
        slots_left = slots["leftToBook"]
        if slots_left == 0:
            waiting_list_length = slots["inWaitingList"]
            click.echo(
                f"{group_activity_name} på {location} {formatted_group_activity_date} är fullbokat. "
                f"Det är {waiting_list_length} {'personer' if waiting_list_length > 1 else 'person'} på reservplats."
            )
            continue

        group_activity_booking = _book_group_activity(group_activity, authorization)
        if not group_activity_booking:
            continue

        group_activity_booking_start = _parse_datetime(group_activity_booking["duration"]["start"])

        click.echo(f"{group_activity_name} på {location} {_format_datetime(group_activity_booking_start)} bokades!")


if __name__ == '__main__':
    friskis()
