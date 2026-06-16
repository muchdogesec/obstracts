# `reprocess_posts_on_feeds.py` Running Guide

`utilities/reprocess_posts_on_feeds.py` is a management API client for feed maintenance jobs. It uses subcommands:

- `reprocess`
- `reextract`
- `reindex`
- `refetch`

## Most Important Arguments

These are the options you will usually care about first:

- `--base-url`: Required. Must be the management API root, for example `https://management.obstracts.staging.signalscorps.com/obstracts_api/admin/api/` or `https://management.obstracts.com/obstracts_api/admin/api/`.
- `--api-key`: Required. Sent as `Authorization: Token <api-key>`.
- `--feed-ids`: Optional. If omitted, the script fetches all feeds from the API and processes them.
- `--ignore-feeds`: Optional. Excludes specific feed IDs from the run.
- `--dry-run`: Shows which feeds would be processed without creating jobs.

Mode-specific highlights:

- `reprocess`: Reprocess posts without running extraction again.
- `reextract`: Re-run extraction and reprocess posts. This is the main mode when you need new extraction output.
- `reindex`: Re-index the post content for posts already in the feed.
- `refetch`: Check for new posts since the last fetch.
- `--profile-id`: Required for `reextract`, `reindex`, and `refetch`.
- `--no-archive`: `refetch` only. Limits the fetch to the live feed URL and skips archive-aware URL discovery.
- `--pubdate-after`: `reprocess` only. Limits reprocessing to posts updated after the given timestamp.

## Usage

General shape:

```bash
python utilities/reprocess_posts_on_feeds.py <subcommand> [options]
```

Examples:

```bash
python utilities/reprocess_posts_on_feeds.py reprocess \
  --base-url https://management.obstracts.staging.signalscorps.com/obstracts_api/admin/api/ \
  --api-key your_api_key \
  --feed-ids <feed-id-1> <feed-id-2>
```

```bash
python utilities/reprocess_posts_on_feeds.py reprocess \
  --base-url https://management.obstracts.staging.signalscorps.com/obstracts_api/admin/api/ \
  --api-key your_api_key \
  --feed-ids <feed-id-1> \
  --pubdate-after 2026-06-16T12:00:00
```

```bash
python utilities/reprocess_posts_on_feeds.py reextract \
  --base-url https://management.obstracts.staging.signalscorps.com/obstracts_api/admin/api/ \
  --api-key your_api_key \
  --profile-id 33333333-3333-3333-3333-333333333333 \
  --feed-ids 11111111-1111-1111-1111-111111111111 \
  --all
```

```bash
python utilities/reprocess_posts_on_feeds.py reindex \
  --base-url https://management.obstracts.staging.signalscorps.com/obstracts_api/admin/api/ \
  --api-key your_api_key \
  --profile-id 33333333-3333-3333-3333-333333333333 \
  --feed-ids 11111111-1111-1111-1111-111111111111 \
  --all
```

```bash
python utilities/reprocess_posts_on_feeds.py refetch \
  --base-url https://management.obstracts.staging.signalscorps.com/obstracts_api/admin/api/ \
  --api-key your_api_key \
  --profile-id 33333333-3333-3333-3333-333333333333 \
  --feed-ids 11111111-1111-1111-1111-111111111111 \
  --no-archive
```

## What the Script Does

1. Builds a `requests.Session`.
2. Sets `Accept: application/json`.
3. Sends your API key as `Authorization: Token ...`.
4. Uses the feed list you pass in, or fetches every feed from `GET /v1/feeds/` if you do not pass `--feed-ids`.
5. Removes any feed IDs listed in `--ignore-feeds`.
6. Deduplicates the final feed list while preserving order.
7. Either:
   - Prints feed details and exits if `--dry-run` is set, or
   - Creates jobs and polls them until completion.
8. Writes a status table to `--status-file` as jobs progress.

## Subcommands

### `reprocess`

Reprocesses posts without running extraction again.

Important behavior:

- Uses `PATCH /v1/feeds/<feed_id>/reprocess-posts/`
- Sends `skip_extraction: true`
- Sends `only_hidden_posts: false`
- Supports `--pubdate-after` to limit reprocessing to posts updated after the given timestamp

This mode is for regenerating STIX objects from existing extraction data.

### `reextract`

Re-runs extraction and then reprocesses the posts.

Required flags:

- `--profile-id`

Optional flags:

- `--all`: reprocess all eligible posts instead of only hidden posts

Payload sent to the API:

- `skip_extraction: false`
- `only_hidden_posts: true` unless `--all` is set
- `profile_id: <profile-id>`

### `reindex`

Re-indexes the content of posts already stored in the feed.

Required flags:

- `--profile-id`

Optional flags:

- `--all`: re-index all eligible posts instead of only hidden posts

Payload sent to the API:

- `profile_id: <profile-id>`
- `only_hidden_posts: true` unless `--all` is set

This mode updates the post content (`description`) and re-runs the extraction pipeline on the new content. It does not update the post metadata fields such as `title`, `pubdate`, `author`, or `categories`.

### `refetch`

Checks for new posts on the blog since the last fetch.

Required flags:

- `--profile-id`

Useful flags:

- `--no-archive`: only check the live feed URL, not archive-discovered URLs
- `--include-remote-blogs`: allow posts from other domains when the feed mixes in remote content
- `--force-full-fetch`: fetch all URLs from the earliest search date instead of only new posts since the last fetch

Defaults:

- `include_remote_blogs=false`
- `force_full_fetch=false`
- `use_feed_url_only=false` unless `--no-archive` is set

Payload sent to the API:

- `profile_id: <profile-id>`
- `include_remote_blogs: <bool>`
- `force_full_fetch: <bool>`
- `use_feed_url_only: <bool>`

## Arguments

### `--base-url` `required`

Must point at the management API root, not the public site.

Valid examples:

```bash
--base-url https://management.obstracts.staging.signalscorps.com/obstracts_api/admin/api/
```

```bash
--base-url https://management.obstracts.com/obstracts_api/admin/api/
```

The script appends endpoints such as:

- `/v1/feeds/`
- `/v1/feeds/<feed_id>/`
- `/v1/feeds/<feed_id>/reprocess-posts/`
- `/v1/feeds/<feed_id>/fetch/`
- `/v1/jobs/<job_id>/`

### `--api-key` `required`

Authentication token used for API requests.

The script sends it as:

```http
Authorization: Token <api-key>
```

If the token is wrong or missing, the first request will fail.

### `--feed-ids`

One or more feed IDs to process.

- If provided, only those feeds are processed.
- If omitted, the script calls `GET /v1/feeds/` and processes every feed returned by the API.

### `--ignore-feeds`

One or more feed IDs to exclude from processing.

Use this when you want to process a broad set of feeds but skip a few specific ones.

### `--dry-run`

Prints the feed names and post counts that would be processed, then exits without creating any jobs.

This is the safest way to validate your feed selection before doing a real run.

### `--pubdate-after`

`reprocess` only.

Limit reprocessing to posts updated after the given timestamp.

The value must be in ISO 8601 format. The script sends it to the API as `pubdate_after`.

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

### `--profile-id`

Required for `reextract`, `reindex`, and `refetch`.

- `reextract` uses it to run extraction again.
- `reindex` uses it to reprocess the post content.
- `refetch` uses it to create the feed update job.

### `--all`

`reextract` and `reindex` only.

When set, the script asks the backend to consider all eligible posts rather than only hidden ones.

## Practical Advice

- Start with `--dry-run` whenever you are unsure about the feed list.
- Make sure `--base-url` points to the management API, not the public site URL.
- Use `reextract` when you want new extraction output.
- Use `reindex` when you want to update the body/content of posts already in the feed.
- Use `refetch` when you want to check for new posts since the last fetch.
- Use `--no-archive` in `refetch` when you only want the live feed URL to be checked.
- Prefer small values for `--max-in-queue` if you are running against a busy or rate-limited environment.
