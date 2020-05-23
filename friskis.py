import json
from datetime import date, datetime, timedelta, time
from pathlib import Path

import click
import requests
from pytz import utc


API_ENDPOINT = "https://bokning.linkoping.friskissvettis.se/brponline/api/ver3"
BUSINESS_UNITS_URL = f"{API_ENDPOINT}/businessunits"
LOGIN_URL = f"{API_ENDPOINT}/auth/login"
LOGIN_CREDENTIALS_PATH = Path(__file__).parent / ".login"


class FriskisException(Exception):
    pass


class FriskisAPIError(FriskisException):
    pass


class BusinessUnitNotFoundError(FriskisAPIError):
    pass


class GroupActivityNotFoundError(FriskisAPIError):
    pass


def _get_business_units():
    business_units_response = requests.get(BUSINESS_UNITS_URL)
    return business_units_response.json()


def _get_business_unit(name):
    for business_unit in _get_business_units():
        if business_unit["name"].lower() == name.lower():
            return business_unit
    raise BusinessUnitNotFoundError(f"A business unit named '{name}' could not be found.")


def _get_group_activities(business_unit, day):
    url = f"{BUSINESS_UNITS_URL}/{business_unit['id']}/groupactivities"
    period_start = datetime.combine(day, time())
    period_end = period_start + timedelta(days=1)
    
    def datetime_to_string(dt):
        dt_as_utc = dt.astimezone(utc)
        date_string = dt_as_utc.strftime("%Y-%m-%d")
        time_string = f"{dt_as_utc.strftime('%H:%M:%S')}"
        return f"{date_string}T{time_string}.000Z"

    params = {
        "period.start": datetime_to_string(period_start),
        "period.end": datetime_to_string(period_end),
    }
    group_activities_response = requests.get(url, params)
    return group_activities_response.json()


def _get_group_activity(name, day, business_unit):
    group_activities = _get_group_activities(business_unit, day)
    for group_activity in group_activities:
        if group_activity["name"].lower() == name.lower():
            return group_activity
    raise GroupActivityNotFoundError(f"A group activity named '{name}' could not be found.")


def _get_login_credentials():
    with open(LOGIN_CREDENTIALS_PATH) as f:
        return json.load(f)


def _login():
    params = _get_login_credentials()
    login_response = requests.post(LOGIN_URL, json=params)
    return login_response.json()


def _book_group_activity(group_activity):
    authorization = _login()
    username = authorization["username"]
    url = f"{API_ENDPOINT}/customers/{username}/bookings/groupactivities"
    params = {
        "groupActivity": group_activity["id"],
        "allowWaitingList": False,
    }
    token_type = authorization["token_type"]
    access_token = authorization["access_token"]
    headers = {
        "authorization": f"{token_type} {access_token}",
    }
    attend_group_activity_response = requests.post(url, json=params, headers=headers)
    if attend_group_activity_response.status_code == 201:
        return attend_group_activity_response.json()
    return {}


@click.command()
@click.argument("business_unit_name")
@click.argument("activity_name")
@click.argument("days_ahead", type=click.INT)
def friskis(business_unit_name, activity_name, days_ahead):
    business_unit = _get_business_unit(business_unit_name)
    today = date.today()
    upcoming_day = today + timedelta(days=days_ahead)
    group_activity = _get_group_activity(activity_name, upcoming_day, business_unit)
    group_activity_booking = _book_group_activity(group_activity)
    click.echo(group_activity_booking)


if __name__ == '__main__':
    friskis()
