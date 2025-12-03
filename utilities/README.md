## Reindex posts

Sometimes if posts fail processing, you can run the following script to update them so that they show properly.

```shell
python3 -m venv obstracts-venv
source obstracts-venv/bin/activate
```

```shell
python3 utilities/reindex_missing_posts.py \
  --base-url hhttp://127.0.0.1:8001/api/v1 \
  --feed-id abc123 \
  --profile-id abc123 \
  --api-key SECRET \
  --max-in-queue 5 \
  --status-file jobs_status.txt \
  --poll-interval 5 \
  --max-wait 3600
```