import json
from datetime import date, datetime, timedelta, time
from pathlib import Path

import click
import requests
from dateutil.parser import parse as fromisoformat
from pytz import timezone, utc

stockholm = timezone("Europe/Stockholm")

API_ENDPOINT = "https://bokning.linkoping.friskissvettis.se/brponline/api/ver3"
BUSINESS_UNITS_URL = f"{API_ENDPOINT}/businessunits"
LOGIN_URL = f"{API_ENDPOINT}/auth/login"
PROJECT_ROOT = Path(__file__).parent
LOGIN_CREDENTIALS_PATH = PROJECT_ROOT / ".login"
SCHEDULE_PATH = PROJECT_ROOT / ".schedule"


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


def _format_datetime(dt, delimiter=" ", tz=stockholm, seconds=False):
    aware = dt.astimezone(tz)
    date_string = aware.date().isoformat()
    time_string = aware.strftime("%H:%M:%S" if seconds else "%H:%M")
    return f"{date_string}{delimiter}{time_string}"


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
    with open(SCHEDULE_PATH) as f:
        return json.load(f)


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


@click.command()
def friskis():
    now = datetime.now(stockholm)
    today = now.date()
    authorization = _login()
    existing_bookings = _get_bookings(authorization)
    for event in _get_schedule():
        group_activity_weekday = event["weekday"]
        group_activity_date = today
        while group_activity_date.isoweekday() != group_activity_weekday:
            group_activity_date += timedelta(days=1)
        
        business_unit_name = event["location"]
        business_unit = _get_business_unit(business_unit_name)

        group_activity_name = event["name"]
        group_activity = _get_group_activity(group_activity_name, group_activity_date, business_unit)
        formatted_group_activity_date = group_activity_date.isoformat()
        if not group_activity:
            click.echo(f"{group_activity_name} är inte schemalagt på {business_unit_name} {formatted_group_activity_date}.")
            continue
        if group_activity["cancelled"]:
            click.echo(f"{group_activity_name} på {business_unit_name} är inställt {formatted_group_activity_date}")

        bookable_earliest = _parse_datetime(group_activity["bookableEarliest"])
        already_booked = group_activity in [booking["groupActivity"] for booking in existing_bookings]
        if now < bookable_earliest or already_booked:
            continue

        slots = group_activity["slots"]
        slots_left = slots["leftToBook"]
        if slots_left == 0:
            waiting_list_length = slots["inWaitingList"]
            click.echo(
                f"{group_activity_name} på {business_unit_name} {formatted_group_activity_date} är fullbokat. "
                f"Det är {waiting_list_length} {'personer' if waiting_list_length > 1 else 'person'} på reservplats."
            )
            continue

        group_activity_booking = _book_group_activity(group_activity, authorization)
        if not group_activity_booking:
            continue

        group_activity_booking_start = _parse_datetime(group_activity_booking["duration"]["start"])

        click.echo(f"{group_activity_name} på {business_unit_name} {_format_datetime(group_activity_booking_start)} bokades!")


if __name__ == '__main__':
    friskis()
