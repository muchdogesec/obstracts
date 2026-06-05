from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse
from typing import Any, Callable, Literal, TypeAlias, cast

import requests

ModeName: TypeAlias = Literal["reprocess", "reextract", "refetch", "reindex"]
JobResponse: TypeAlias = dict[str, Any]
ArgsHandler: TypeAlias = Callable[[requests.Session, str, str, "Args"], JobResponse]

@dataclass(slots=True, kw_only=True)
class Args:
    mode: ModeName
    base_url: str
    api_key: str
    feed_ids: list[str] | None = None
    ignore_feeds: list[str] | None = None
    dry_run: bool = False
    max_in_queue: int = 3
    status_file: str = "reindex_status.md"
    poll_interval: int = 10
    max_wait: int = 3600
    profile_id: str | None = None
    all: bool = False
    include_remote_blogs: bool = False
    force_full_fetch: bool = False
    no_archive: bool = False
    function: ArgsHandler


def fetch_feed_ids(session: requests.Session, base_url: str) -> list[str]:
    url = f"{base_url}/v1/feeds/"
    params = {"page": 1}
    feed_ids: list[str] = []
    while True:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data["page_results_count"] == 0:
            break
        params["page"] += 1
        feed_ids.extend([x["id"] for x in data.get("results") or data["feeds"]])
    return feed_ids


def fetch_feed_details(
    session: requests.Session,
    base_url: str,
    feed_id: str,
) -> dict[str, Any]:
    url = f"{base_url}/v1/feeds/{feed_id}/"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def reprocess(
    session: requests.Session,
    base_url: str,
    feed_id: str,
    args: Args,
) -> JobResponse:
    url = f"{base_url}/v1/feeds/{feed_id}/reprocess-posts/"
    payload: dict[str, Any] = {
        "skip_extraction": True,
        "only_hidden_posts": False,
    }
    resp = session.patch(url, json=payload)
    resp.raise_for_status()
    return resp.json()


def reextract(
    session: requests.Session,
    base_url: str,
    feed_id: str,
    args: Args,
) -> JobResponse:
    url = f"{base_url}/v1/feeds/{feed_id}/reprocess-posts/"
    payload: dict[str, Any] = {
        "skip_extraction": False,
        "only_hidden_posts": not args.all,
        "profile_id": args.profile_id,
    }
    resp = session.patch(url, json=payload)
    resp.raise_for_status()
    return resp.json()

def refetch(
    session: requests.Session,
    base_url: str,
    feed_id: str,
    args: Args,
) -> JobResponse:
    url = f"{base_url}/v1/feeds/{feed_id}/fetch/"
    payload: dict[str, Any] = {
        "profile_id": args.profile_id,
        "include_remote_blogs": args.include_remote_blogs,
        "force_full_fetch": args.force_full_fetch,
        "use_feed_url_only": args.no_archive,
    }
    resp = session.patch(url, json=payload)
    resp.raise_for_status()
    return resp.json()


def reindex(
    session: requests.Session,
    base_url: str,
    feed_id: str,
    args: Args,
) -> JobResponse:
    url = f"{base_url}/v1/feeds/{feed_id}/posts/reindex/"
    payload: dict[str, Any] = {
        "profile_id": args.profile_id,
        "only_hidden_posts": not args.all,
    }
    resp = session.patch(url, json=payload)
    resp.raise_for_status()
    return resp.json()


def get_real_job(session, base_url, job_data):
    if active_job_id := job_data.get('active_job_id'):
        url = f"{base_url}/v1/jobs/{active_job_id}/"
        resp = session.get(url)
        resp.raise_for_status()
        return resp.json()
    return job_data



def write_status_file(results: dict[str, JobResponse], status_file: str) -> None:
    lines: list[tuple[str, str, str, str, str]] = []
    for feed_id, job in results.items():
        status = job["state"]
        job_id = job["id"]
        lines.append(
            (
                status.ljust(11),
                str(job.get("created")).ljust(27),
                str(job.get("completion_time")).ljust(27),
                str(feed_id),
                str(job_id),
            )
        )

    lines.sort()

    with open(status_file, "w", encoding="utf-8") as fh:
        fh.write("|    status  |       start_time            |  completion_time            | feed_id                              | job_id                              |\n")
        fh.write("|------------|-----------------------------|-----------------------------|--------------------------------------|-------------------------------------|\n")
        for line in lines:
            fh.write("|" + (" | ".join(line)) + "|\n")


def poll_jobs(
    session: requests.Session,
    base_url: str,
    feed_ids: list[str],
    *,
    max_in_queue: int,
    status_file: str,
    poll_interval: int,
    max_wait: int,
    args: Args,
) -> dict[str, JobResponse]:
    results: dict[str, JobResponse] = {}
    in_queue: set[str] = set()
    start = time.time()

    while True:
        if feed_ids and (len(in_queue) <= max_in_queue - 1):
            feed_id = feed_ids.pop()
            print(f"running {args.mode} on feed {feed_id}")
            job = args.function(session, base_url, feed_id, args)
            job = get_real_job(session, base_url, job)
            results[feed_id] = job
            in_queue.add(job["id"])

        for job_id in list(in_queue):
            try:
                url = f"{base_url}/v1/jobs/{job_id}/"
                resp = session.get(url)
                resp.raise_for_status()
                job: JobResponse = resp.json()

                status = job["state"]
                feed_id = job["feed_id"]
                results[feed_id] = job
                print(f"Job {job_id} status: {status}")
                if status not in ["processing", "retrieving", "in-queue"]:
                    print(f"Job {job_id} completed with status: {status}")
                    in_queue.discard(job_id)
                write_status_file(results, status_file)
            except Exception as exc:
                print(f"Error fetching job {job_id}: {exc}")

        if not in_queue and not feed_ids:
            print("All jobs processed")
            break

        if time.time() - start > max_wait:
            print("Timeout reached while waiting for jobs to finish")
            break

        time.sleep(poll_interval)

    write_status_file(results, status_file)
    return results


def parse_args() -> Args:
    parser = argparse.ArgumentParser(description="Reprocess feeds")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--base-url",
        required=True,
        help="Management API base URL, for example https://management.obstracts.com/obstracts_api/admin/api/",
        type=lambda url: url.rstrip('/'),
    )
    common.add_argument("--api-key", required=True)
    common.add_argument(
        "--feed-ids",
        nargs="+",
        default=None,
        help="List of feed IDs to process (if omitted, all feeds are fetched from the API)",
    )
    common.add_argument(
        "--ignore-feeds",
        nargs="+",
        default=None,
        help="List of feed IDs to ignore/exclude from processing",
    )
    common.add_argument(
        "--dry-run",
        action="store_true",
        help="Print feeds that will be processed without actually processing them",
    )
    common.add_argument("--max-in-queue", type=int, default=3)
    common.add_argument("--status-file", default="reindex_status.md")
    common.add_argument("--poll-interval", type=int, default=10)
    common.add_argument("--max-wait", type=int, default=3600)

    subparsers = parser.add_subparsers(dest="mode", required=True)

    reprocess_parser = subparsers.add_parser(
        "reprocess",
        parents=[common],
        help="Reprocess posts without running extraction again",
    )
    reprocess_parser.set_defaults(function=reprocess)

    reextract_parser = subparsers.add_parser(
        "reextract",
        parents=[common],
        help="Re-run extraction and reprocess posts",
    )
    reextract_parser.add_argument(
        "--profile-id",
        required=True,
        help="Profile to use for extraction",
    )
    reextract_parser.add_argument(
        "--all",
        action="store_true",
        help="Run on all eligible posts instead of only hidden posts",
    )
    reextract_parser.set_defaults(function=reextract)

    reindex_parser = subparsers.add_parser(
        "reindex",
        parents=[common],
        help="Re-index the content of posts already in the feed",
    )
    reindex_parser.add_argument(
        "--profile-id",
        required=True,
        help="Profile to use for re-indexing",
    )
    reindex_parser.add_argument(
        "--all",
        action="store_true",
        help="Run on all eligible posts instead of only hidden posts",
    )
    reindex_parser.set_defaults(function=reindex)

    refetch_parser = subparsers.add_parser(
        "refetch",
        parents=[common],
        help="Check for new posts since the last fetch",
    )
    refetch_parser.add_argument(
        "--profile-id",
        required=True,
        help="Profile to use for the fetch job",
    )
    refetch_parser.add_argument(
        "--include-remote-blogs",
        action="store_true",
        help="Allow history4feed to include remote posts from other domains",
    )
    refetch_parser.add_argument(
        "--force-full-fetch",
        action="store_true",
        help="Fetch all URLs from the earliest search date instead of only new posts since the last fetch",
    )
    refetch_parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Only check the live feed URL instead of considering archived URLs too",
    )
    refetch_parser.set_defaults(function=refetch)

    ns = parser.parse_args()
    args = Args(
        mode=cast(ModeName, ns.mode),
        base_url=ns.base_url,
        api_key=ns.api_key,
        feed_ids=ns.feed_ids,
        ignore_feeds=ns.ignore_feeds,
        dry_run=ns.dry_run,
        max_in_queue=ns.max_in_queue,
        status_file=ns.status_file,
        poll_interval=ns.poll_interval,
        max_wait=ns.max_wait,
        profile_id=getattr(ns, "profile_id", None),
        all=getattr(ns, "all", False),
        include_remote_blogs=getattr(ns, "include_remote_blogs", False),
        force_full_fetch=getattr(ns, "force_full_fetch", False),
        no_archive=getattr(ns, "no_archive", False),
        function=cast(ArgsHandler, ns.function),
    )
    return args


def main() -> int:
    args: Args = parse_args()

    session = requests.Session()
    session.headers["Accept"] = "application/json"
    # session.headers["api-key"] = args.api_key
    session.headers["Authorization"] = "Token " + args.api_key

    if not args.feed_ids:
        args.feed_ids = fetch_feed_ids(session, args.base_url)

    # Filter out ignored feeds
    if args.ignore_feeds:
        ignore_set = set(args.ignore_feeds)
        original_count = len(args.feed_ids)
        args.feed_ids = [fid for fid in args.feed_ids if fid not in ignore_set]
        ignored_count = original_count - len(args.feed_ids)
        if ignored_count > 0:
            print(f"Ignoring {ignored_count} feed(s)")

    args.feed_ids = list(dict.fromkeys(args.feed_ids))

    print(f"Processing {len(args.feed_ids)} feed(s): {', '.join(args.feed_ids)}")

    # Dry run: fetch and display feed details
    if args.dry_run:
        print("\nDry run mode - Feeds that will be processed:\n")
        for feed_id in args.feed_ids:
            try:
                feed_details = fetch_feed_details(session, args.base_url, feed_id)
                if 'obstract_feed_metadata' in feed_details:
                    feed_details = feed_details['obstract_feed_metadata']
                feed_name = feed_details['title']
                print(f"{feed_id}: {feed_name}. {feed_details['count_of_posts']} posts")
            except Exception as exc:
                print(f"{feed_id}: Error fetching details - {exc}")
        print(f"\nTotal feeds to process: {len(args.feed_ids)}")
        return 0

    print("\nStarting processing of feeds...\n")
    print("Writing status to:", args.status_file)
    results = poll_jobs(
        session,
        args.base_url,
        list(args.feed_ids),
        max_in_queue=args.max_in_queue,
        status_file=args.status_file,
        poll_interval=args.poll_interval,
        max_wait=args.max_wait,
        args=args,
    )

    print(f"\nProcessing complete. Results written to {args.status_file}\n")

    print("All jobs processed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
