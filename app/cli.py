from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import ensure_directories
from app.jobs import run_afjord_once, run_indre_fosen_once, run_orland_once, run_osen_once
from db.database import init_db


def _parse_hours(value: str) -> set[int]:
    hours: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        hour = int(item)
        if hour < 0 or hour > 23:
            raise argparse.ArgumentTypeError("Timer må være mellom 0 og 23.")
        hours.add(hour)
    if not hours:
        raise argparse.ArgumentTypeError("Oppgi minst én time.")
    return hours


def main() -> None:
    parser = argparse.ArgumentParser(description="Kjor robotjournalist-jobber.")
    parser.add_argument(
        "--municipality",
        choices=["indre-fosen", "osen", "afjord", "orland"],
        default="indre-fosen",
        help="Hvilken kommune som skal prosesseres.",
    )
    parser.add_argument("--force", action="store_true", help="Prosesser selv om dokumentet er sett for.")
    parser.add_argument(
        "--protocol-index",
        type=int,
        default=0,
        help="0 er beste/siste treff. 1 er neste protokoll i lista.",
    )
    parser.add_argument(
        "--only-at-hours",
        type=_parse_hours,
        help="Kjor bare ved disse lokale timene, f.eks. 8,12.",
    )
    parser.add_argument(
        "--timezone",
        default="Europe/Oslo",
        help="Tidssone for --only-at-hours.",
    )
    args = parser.parse_args()

    now = datetime.now(ZoneInfo(args.timezone))
    if args.only_at_hours and now.hour not in args.only_at_hours:
        result = {
            "status": "skipped_schedule",
            "reason": "Jobben kjører ikke på dette klokkeslettet.",
            "local_time": now.isoformat(timespec="minutes"),
            "allowed_hours": sorted(args.only_at_hours),
            "email_sent": False,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    ensure_directories()
    init_db()
    if args.municipality == "osen":
        result = asyncio.run(run_osen_once(force=args.force, protocol_index=args.protocol_index))
    elif args.municipality == "afjord":
        result = asyncio.run(run_afjord_once(force=args.force, protocol_index=args.protocol_index))
    elif args.municipality == "orland":
        result = asyncio.run(run_orland_once(force=args.force, protocol_index=args.protocol_index))
    else:
        result = asyncio.run(run_indre_fosen_once(force=args.force, protocol_index=args.protocol_index))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
