from __future__ import annotations

import signal
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from threading import Event, Thread
from time import sleep
from typing import TYPE_CHECKING

from friskis import env
from friskis.cli.utils import ensure_existing_directory
from friskis.constants import TZ
from friskis.utils import logging
from friskis.utils.logging import logger

from .constants import ACTIVITY_REFRESH_INTERVAL, AUTHORIZATION_REFRESH_INTERVAL
from .utils import (
    authorize_profile,
    book,
    initialize_activities,
    is_bookable,
    is_time_to_book,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import FrameType

__all__ = [
    "main",
]


def _run(profile_location: Path, shutdown: Event) -> None:
    authorization = authorize_profile(profile_location)
    activities = initialize_activities(profile_location)
    last_authorization_refresh_at = last_activity_refresh_at = datetime.now(TZ)
    logger.debug(f"Waiting for upcoming activities for {profile_location.stem}...")
    while not shutdown.is_set():
        if not activities:
            sleep(60)
            continue
        for activity in list(activities.values()):
            if not is_time_to_book(activity):
                continue
            if not is_bookable(activity, authorization):
                del activities[activity.id]
                continue
            while book(activity, authorization) == "too_early":
                sleep(0.02)
        sleep(1)
        if last_authorization_refresh_at < datetime.now(TZ) - AUTHORIZATION_REFRESH_INTERVAL:
            authorization = authorize_profile(profile_location)
            last_authorization_refresh_at = datetime.now(TZ)
        if last_activity_refresh_at < datetime.now(TZ) - ACTIVITY_REFRESH_INTERVAL:
            activities.update(initialize_activities(profile_location))
            last_activity_refresh_at = datetime.now(TZ)

    logger.debug(f"Stopped waiting for upcoming activities for {profile_location.stem}.")


def _launch(profile_locations: Sequence[Path]) -> None:
    shutdown = Event()

    def handle_interrupt(sig: int, frame: FrameType | None) -> None:
        shutdown.set()
        logger.debug("Waiting for requests to finish...")

    signal.signal(signal.SIGTERM, handle_interrupt)
    signal.signal(signal.SIGINT, handle_interrupt)

    threads = [Thread(target=_run, args=(profile_location, shutdown)) for profile_location in profile_locations]

    for thread in threads:
        thread.start()

    while not shutdown.is_set():
        sleep(1)

    for thread in threads:
        thread.join()


def main() -> None:
    parser = ArgumentParser(description="Daemonized reservation of slots at Friskis & Svettis activities.")
    parser.add_argument(
        "profiles",
        nargs="*",
        default=list(Path(env.PROFILES_LOCATION).iterdir()),
        type=ensure_existing_directory,
    )
    parser.add_argument("--debug", default=False, action="store_true")
    args = parser.parse_args()

    logging.configure(args.debug)

    _launch(args.profiles)
