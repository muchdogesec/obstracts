## Reindex posts (web only)

Sometimes if posts fail processing, you can run the following script to update them so that they show properly.

```shell
python3 -m venv obstracts-venv
source obstracts-venv/bin/activate
```

```shell
python reprocess_posts_on_feeds.py --base-url '<MANAGEMENT API UP TO AND INCLUDING API>' --api-key '[TOKEN]' --max-in-queue 5 --dry-run
```