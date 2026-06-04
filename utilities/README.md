# `reprocess_posts_on_feeds.py` Running Guide

`utilities/reprocess_posts_on_feeds.py` is a small client script that talks to the Obstracts API and creates reprocessing jobs for one or more feeds. It can either:

- Reprocess posts using the existing extraction data.
- Re-extract posts with a specific profile.
- Dry-run the selected feeds and show what would be processed.

## Most Important Arguments

These are the options you will usually care about first:

- `--base-url`: Required. The management API base URL, for example `https://management.obstracts.com/obstracts_api/admin/api/`.
- `--api-key`: Required. Sent as `Authorization: Token <api-key>`.
- `--mode`: Required. Chooses the behavior of the script.
- `--feed-ids`: Optional. If omitted, the script fetches all feeds from the API and processes them.
- `--profile-id`: Required for `reextract`. Also required by the script for `refetch`, although `refetch` is currently not implemented.
- `--all`: Mostly affects `reextract`; it expands the job from hidden posts only to all eligible posts.
- `--dry-run`: Shows which feeds would be processed without creating jobs.

## Usage

```bash
python utilities/reprocess_posts_on_feeds.py \
  --base-url https://<URL>/obstracts_api/admin/api/ \
  --api-key your_api_key \
  --mode reprocess \
  --feed-ids <feed-id-1> <feed-id-2>
```

For a dry run:

```bash
python utilities/reprocess_posts_on_feeds.py \
  --base-url https://<URL>/obstracts_api/admin/api/ \
  --api-key your_api_key \
  --mode reprocess \
  --dry-run
```

## What the Script Does

1. Builds a `requests.Session`.
2. Sets `Accept: application/json`.
3. Sends your API key as `Authorization: Token ...`.
4. Uses the feed list you pass in, or fetches every feed from `GET /v1/feeds/` if you do not pass `--feed-ids`.
5. Removes any feed IDs listed in `--ignore-feeds`.
6. Deduplicates the final feed list.
7. Either:
   - Prints feed details and exits if `--dry-run` is set, or
   - Creates reprocessing jobs and polls them until completion.
8. Writes a status table to `--status-file` as jobs progress.

## Arguments

### `--mode` `required`

Chooses which API payload is sent to `/v1/feeds/<feed_id>/reprocess-posts/`.

Available values:

- `reprocess`: Reprocess posts without running extraction again. This sets `skip_extraction=True`.
- `reextract`: Re-run extraction and then reprocess. This sets `skip_extraction=False` and sends `profile_id`.
- `refetch`: Marked as "not available" in the script and raises `NotImplementedError` if used.

This is the main switch that determines what kind of job gets created.

### `--base-url` `required`

The management API root URL.

Example:

```bash
--base-url https://<URL>/obstracts_api/admin/api/
```

Production example:

```bash
--base-url https://management.obstracts.com/obstracts_api/admin/api/
```

The script appends endpoints such as:

- `/v1/feeds/`
- `/v1/feeds/<feed_id>/`
- `/v1/feeds/<feed_id>/reprocess-posts/`
- `/v1/jobs/<job_id>/`

### `--api-key` `required`

Authentication token used for the API request.

The script sends it as:

```http
Authorization: Token <api-key>
```

If the token is wrong or missing, the first API request will fail.

### `--feed-ids`

One or more feed IDs to process.

- If provided, only those feeds are processed.
- If omitted, the script calls `GET /v1/feeds/` and processes every feed returned by the API.

Notes:

- The help text says "maximum 5", but the script does not enforce that limit directly.
- Duplicate feed IDs are removed before processing.

### `--ignore-feeds`

One or more feed IDs to exclude from processing.

Use this when you want to process a broad set of feeds but skip a few specific ones.

Example:

```bash
--ignore-feeds <feed-id-a> <feed-id-b>
```

### `--profile-id`

Required when the selected mode needs a profile.

- Required by the script for `reextract`.
- Also required by the script for `refetch`, but `refetch` is not implemented.

When `--mode reprocess` is used, this is not needed.

### `--all`

By default, `--all` is off.

For `reextract`, setting `--all` expands the request to all eligible posts instead of only hidden ones.

For `reprocess`, the script always uses the existing extraction data path and does not rely on `--all`.

### `--dry-run`

Prints the feed names and post counts that would be processed, then exits without creating any jobs.

This is the safest way to validate your feed selection before doing a real run.

### `--max-in-queue`

Default: `3`

Controls how many jobs the script tries to keep in flight at once.

Lower values are safer and gentler on the backend. Higher values can speed things up, but may increase API load.

### `--status-file`

Default: `reindex_status.md`

Path to the Markdown file where the script writes job status updates.

The file contains a table with:

- Job status
- Start time
- Completion time
- Feed ID
- Job ID

### `--poll-interval`

Default: `10`

Number of seconds to wait between job status checks.

Lower values update the status file more frequently, but increase API traffic.

### `--max-wait`

Default: `3600`

Maximum number of seconds to wait for jobs to finish before the script exits.

If jobs run longer than this, the script stops polling and reports a timeout.

## Example Commands

Process two feeds, reprocessing only hidden/unprocessed posts:

```bash
python utilities/reprocess_posts_on_feeds.py \
  --base-url https://<URL>/obstracts_api/admin/api/ \
  --api-key your-token \
  --mode reprocess \
  --feed-ids 11111111-1111-1111-1111-111111111111 22222222-2222-2222-2222-222222222222
```

Re-extract posts using a specific profile:

```bash
python utilities/reprocess_posts_on_feeds.py \
  --base-url https://<URL>/obstracts_api/admin/api/ \
  --api-key your-token \
  --mode reextract \
  --profile-id 33333333-3333-3333-3333-333333333333 \
  --feed-ids 11111111-1111-1111-1111-111111111111 \
  --all
```

Dry-run all feeds except one:

```bash
python utilities/reprocess_posts_on_feeds.py \
  --base-url https://<URL>/obstracts_api/admin/api/ \
  --api-key your-token \
  --mode reprocess \
  --ignore-feeds 44444444-4444-4444-4444-444444444444 \
  --dry-run
```

## Backend Behavior To Know

The API endpoint behind this script is the feed reprocess endpoint:

- `PATCH /v1/feeds/<feed_id>/reprocess-posts/`

The request payload depends on the selected mode:

- `reprocess` sends:
  - `skip_extraction: true`
  - `only_hidden_posts: false`
- `reextract` sends:
  - `skip_extraction: false`
  - `profile_id: <profile-id>`
  - `only_hidden_posts: true` unless `--all` is set

On the server side, `only_hidden_posts` controls whether the job targets only hidden/unprocessed posts or the whole feed. The server also requires `profile_id` when `skip_extraction` is `false`.

## Status File

During execution, the script writes a Markdown table to `--status-file`.

This file is updated while jobs are polled and includes the latest known state for each feed/job pair. If you are running a large batch, this file is the easiest place to check progress without re-running the script.

## Practical Advice

- Start with `--dry-run` whenever you are unsure about the feed list.
- Make sure `--base-url` points to the management API, not the public site URL.
- Use `--all` carefully, because it can expand a re-extraction run from hidden posts only into all eligible posts.
- Prefer small values for `--max-in-queue` if you are running against a busy or rate-limited environment.
- Use `reprocess` for regenerating STIX objects from existing extractions, and `reextract` when you need extraction to run again with a chosen profile.
