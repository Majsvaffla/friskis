import json
import sys
from argparse import ArgumentParser, ArgumentTypeError, Namespace
from datetime import time

from friskis import env
from friskis.api import actions as api
from friskis.api.models import Customer
from friskis.constants import CREDENTIALS_FILE_NAME, SCHEDULE_FILE_NAME
from friskis.daemon.models import Credentials, ScheduleEntry
from friskis.daemon.utils import _read_schedule
from friskis.utils import logging

__all__ = [
    "main",
]


def _profile_add(args: Namespace) -> None:
    credentials = Credentials(email=args.email, password=args.password or input("Password: "))
    customer = api.get_customer(api.log_in(**credentials.model_dump()))
    if customer.profile_location.exists():
        print(f"{customer.profile_location} already exists.", file=sys.stderr)
        exit(1)
    customer.profile_location.mkdir()
    (customer.profile_location / CREDENTIALS_FILE_NAME).write_text(credentials.model_dump_json(), encoding="utf8")
    (customer.profile_location / SCHEDULE_FILE_NAME).write_text(json.dumps([]), encoding="utf8")
    print(customer.profile_location.name)


def _profile_list(args: Namespace) -> None:
    for directory in env.PROFILES_LOCATION.iterdir():
        print(directory.name)


def _profile_remove(args: Namespace) -> None:
    customer = Customer.from_profile_identifier(args.profile)
    (customer.profile_location / SCHEDULE_FILE_NAME).unlink()
    (customer.profile_location / CREDENTIALS_FILE_NAME).unlink()
    customer.profile_location.rmdir()


def _schedule_add(args: Namespace) -> None:
    customer = Customer.from_profile_identifier(args.profile)
    entry_to_add = ScheduleEntry(weekday=args.weekday, name=args.activity, location=args.location, time=args.time)
    existing_entries = _read_schedule(customer.profile_location)
    if entry_to_add not in existing_entries:
        (customer.profile_location / SCHEDULE_FILE_NAME).write_text(
            json.dumps(
                [{**entry.model_dump(), "time": entry.time.isoformat()} for entry in (*existing_entries, entry_to_add)]
            ),
            encoding="utf8",
        )


def _schedule_list(args: Namespace) -> None:
    customer = Customer.from_profile_identifier(args.profile)
    for entry in _read_schedule(customer.profile_location):
        print(entry.name, entry.location, entry.weekday, entry.time, sep="\t")


def _schedule_remove(args: Namespace) -> None:
    customer = Customer.from_profile_identifier(args.profile)
    entry_to_remove = ScheduleEntry(weekday=args.weekday, name=args.activity, location=args.location, time=args.time)
    existing_entries = _read_schedule(customer.profile_location)
    (customer.profile_location / SCHEDULE_FILE_NAME).write_text(
        json.dumps(
            [
                {**entry.model_dump(), "time": entry.time.isoformat()}
                for entry in existing_entries
                if entry != entry_to_remove
            ]
        ),
        encoding="utf8",
    )


def _iso_formatted_time(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise ArgumentTypeError(f"Invalid time format: {value}") from None


def main() -> None:
    env.PROFILES_LOCATION.mkdir(exist_ok=True)

    root_parser = ArgumentParser(description="Manage schedule of activities for Friskis & Svettis daemon.")
    root_parser.add_argument("--debug", default=False, action="store_true")
    root_subparsers = root_parser.add_subparsers()

    profile_parser = root_subparsers.add_parser("profile")
    profile_subparsers = profile_parser.add_subparsers()

    profile_add_parser = profile_subparsers.add_parser("add")
    profile_add_parser.set_defaults(func=_profile_add)
    profile_add_parser.add_argument("email")
    profile_add_parser.add_argument(
        "password", default=None, nargs="?", help="If omitted, a prompt will request a value."
    )

    profile_list_parser = profile_subparsers.add_parser("list")
    profile_list_parser.set_defaults(func=_profile_list)

    profile_remove_parser = profile_subparsers.add_parser("remove")
    profile_remove_parser.set_defaults(func=_profile_remove)
    profile_remove_parser.add_argument("profile", help="Profile identifier as shown in profile list.")

    schedule_parser = root_subparsers.add_parser("schedule")
    schedule_subparsers = schedule_parser.add_subparsers()

    schedule_add_parser = schedule_subparsers.add_parser("add")
    schedule_add_parser.set_defaults(func=_schedule_add)
    schedule_add_parser.add_argument("profile", help="Profile identifier as shown in profile list.")
    schedule_add_parser.add_argument("activity", help="Name of the activity as shown in the app.")
    schedule_add_parser.add_argument("location", help="Name of the activity location as shown in the app.")
    schedule_add_parser.add_argument("weekday", help="Number of the activity date ISO weekday.")
    schedule_add_parser.add_argument("time", type=_iso_formatted_time, help="Time of the activity in ISO format.")

    schedule_list_parser = schedule_subparsers.add_parser("list")
    schedule_list_parser.set_defaults(func=_schedule_list)
    schedule_list_parser.add_argument("profile", help="Profile identifier as shown in profile list.")

    schedule_remove_parser = schedule_subparsers.add_parser("remove")
    schedule_remove_parser.set_defaults(func=_schedule_remove)
    schedule_remove_parser.add_argument("profile", help="Profile identifier as shown in profile list.")
    schedule_remove_parser.add_argument("activity", help="Name of the activity as shown in the app.")
    schedule_remove_parser.add_argument("location", help="Name of the activity location as shown in the app.")
    schedule_remove_parser.add_argument("weekday", help="Number of the activity date ISO weekday.")
    schedule_remove_parser.add_argument("time", type=_iso_formatted_time, help="Time of the activity in ISO format.")

    args = root_parser.parse_args()

    logging.configure(args.debug)

    args.func(args)
