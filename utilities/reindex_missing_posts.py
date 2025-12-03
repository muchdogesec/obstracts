from __future__ import annotations

import argparse
import time
from typing import List, Optional, Dict, Any

import requests


def fetch_posts(session: requests.Session, base_url: str, feed_id: str) -> List[dict]:
    url = f"{base_url.rstrip('/')}/v1/feeds/{feed_id}/posts/"
    params = {"show_hidden_posts": "true", "page": 1}
    posts = []
    while True:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data['page_results_count'] == 0:
            break
        params['page'] += 1
        posts.extend(data["posts"])
    return posts


def send_reindex(
    session: requests.Session,
    base_url: str,
    feed_id: str,
    post_id: str,
    profile_id: Optional[str]
) -> dict:
    url = f"{base_url.rstrip('/')}/v1/feeds/{feed_id}/posts/{post_id}/reindex/"
    payload = {}
    if profile_id:
        payload["profile_id"] = profile_id
    resp = session.patch(url, json=payload)
    resp.raise_for_status()
    return resp.json()


def write_status_file(results: dict, status_file: str) -> None:
    lines = []
    for post_id, job in results.items():
        status = job['state']
        job_id = job['id']
        lines.append((status.ljust(24), str(job.get('completion_time')).ljust(25), str(post_id), str(job_id)))

    lines.sort()

    with open(status_file, "w", encoding="utf-8") as fh:
        fh.write("|      status   |  completion_time | post_id | job_id |\n")
        fh.write("|---------------|------------------|---------|--------|\n")
        for line in lines:
            fh.write("|" + (" | ".join(line)) + "|\n")


def poll_jobs(
    session: requests.Session,
    base_url: str,
    feed_id: str,
    profile_id: Optional[str],
    post_ids: list[str],
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
        if post_ids and (len(in_queue) <= max_in_queue - 1):
            post_id = post_ids.pop()
            job = send_reindex(session, base_url, feed_id, post_id, profile_id)
            results[post_id] = job
            in_queue.add(job['id'])

        for job_id in list(in_queue):
            try:
                url = f"{base_url.rstrip('/')}/v1/jobs/{job_id}/"
                resp = session.get(url)
                resp.raise_for_status()
                job = resp.json()
            except Exception as exc:
                print(f"Error fetching job {job_id}: {exc}")
                job = None

            if job:
                status = job['state']
                results[job_id] = job
                print(f"Job {job_id} status: {status}")
                if status not in ["processing", "retrieving"]:
                    in_queue.discard(job_id)

        if not in_queue and not post_ids:
            break

        if time.time() - start > max_wait:
            print("Timeout reached while waiting for jobs to finish")
            break

        write_status_file(results, status_file)
        time.sleep(poll_interval)

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reindex non-visible posts")

    parser.add_argument("--base-url", required=True)
    parser.add_argument("--feed-id", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--api-key", required=True)

    parser.add_argument("--max-in-queue", type=int, required=True)
    parser.add_argument("--status-file", required=True)
    parser.add_argument("--poll-interval", type=int, required=True)
    parser.add_argument("--max-wait", type=int, required=True)

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    session = requests.Session()
    session.headers["Accept"] = "application/json"
    session.headers["Authorization"] = "Token " + args.api_key

    try:
        posts = fetch_posts(session, args.base_url, args.feed_id)
    except Exception as exc:
        print(f"Failed to fetch posts: {exc}")
        return 2

    non_visible = [p['id'] for p in posts if not p.get("visible")]
    print(f"Found {len(non_visible)} non-visible posts to reindex")
    print(f"Skipping {len(posts) - len(non_visible)} visible posts")

    results = poll_jobs(
        session,
        args.base_url,
        args.feed_id,
        args.profile_id,
        non_visible,
        max_in_queue=args.max_in_queue,
        status_file=args.status_file,
        poll_interval=args.poll_interval,
        max_wait=args.max_wait,
    )

    failed = [
        jid for jid, job in results.items()
        if job['state'] != "processed"
    ]

    if failed:
        print("Some jobs did not reach 'processed' state within the time limit")
        return 3

    print("All jobs processed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
