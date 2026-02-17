from __future__ import annotations

import argparse
import time
from typing import List, Optional, Dict, Any

import requests


def fetch_feed_ids(session: requests.Session, base_url: str) -> List[str]:
    url = f"{base_url.rstrip('/')}/v1/feeds/"
    params = {"page": 1}
    feed_ids = []
    while True:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data["page_results_count"] == 0:
            break
        params["page"] += 1
        feed_ids.extend([x["id"] for x in data.get("results") or data["feeds"]])
    return feed_ids


def fetch_feed_details(session: requests.Session, base_url: str, feed_id: str) -> dict:
    url = f"{base_url.rstrip('/')}/v1/feeds/{feed_id}/"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def send_reindex(
    session: requests.Session,
    base_url: str,
    feed_id: str,
) -> dict:
    url = f"{base_url.rstrip('/')}/v1/feeds/{feed_id}/reprocess-posts/"
    payload = {
        "skip_extraction": True,
        "only_hidden_posts": False,
    }
    resp = session.patch(url, json=payload)
    resp.raise_for_status()
    return resp.json()


def write_status_file(results: dict, status_file: str) -> None:
    lines = []
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
) -> dict:
    results: dict[str, dict] = {}
    in_queue = set()
    start = time.time()

    while True:
        if feed_ids and (len(in_queue) <= max_in_queue - 1):
            feed_id = feed_ids.pop()
            job = send_reindex(session, base_url, feed_id)
            results[feed_id] = job
            in_queue.add(job["id"])

        for job_id in list(in_queue):
            try:
                url = f"{base_url.rstrip('/')}/v1/jobs/{job_id}/"
                resp = session.get(url)
                resp.raise_for_status()
                job = resp.json()

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
                job = None

        if not in_queue and not feed_ids:
            print("All jobs processed")
            break

        if time.time() - start > max_wait:
            print("Timeout reached while waiting for jobs to finish")
            break

        time.sleep(poll_interval)

    write_status_file(results, status_file)
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reindex feeds")

    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--feed-ids",
        nargs="+",
        default=None,
        help="List of feed IDs to reindex (maximum 5)",
    )
    parser.add_argument(
        "--ignore-feeds",
        nargs="+",
        default=None,
        help="List of feed IDs to ignore/exclude from processing",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print feeds that will be processed without actually processing them",
    )
    parser.add_argument("--api-key", required=True)

    parser.add_argument("--max-in-queue", type=int, default=3)
    parser.add_argument("--status-file", default="reindex_status.md")
    parser.add_argument("--poll-interval", type=int, default=10)
    parser.add_argument("--max-wait", type=int, default=3600)

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    session = requests.Session()
    session.headers["Accept"] = "application/json"
    # session.headers["api-key"] = args.api_key
    session.headers["Authorization"] = "Token " + args.api_key
    print(session.headers)

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

    args.feed_ids = list(set(args.feed_ids))

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

    print("\nStarting reindexing of feeds...\n")
    print("Writing status to:", args.status_file)
    results = poll_jobs(
        session,
        args.base_url,
        list(args.feed_ids),
        max_in_queue=args.max_in_queue,
        status_file=args.status_file,
        poll_interval=args.poll_interval,
        max_wait=args.max_wait,
    )

    failed = [jid for jid, job in results.items() if job["state"] != "processed"]

    print(f"\nReindexing complete. Results written to {args.status_file}\n")

    print("All jobs processed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())