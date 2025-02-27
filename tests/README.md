# Tests

## Setup

To test Obstracts we use a Jekyll blog we've created for exactly this purpose.

https://github.com/muchdogesec/fakeblog123

You can clone this repo, and then setup with Github pages to get a blog running online that you can use.

```shell
python3 -m venv obstracts-venv
source obstracts-venv/bin/activate
# install requirements
pip3 install -r requirements.txt
````

## API schema tests

```shell
st run --checks all http://127.0.0.1:8001/api/schema --generation-allow-x00 true
```


## Run tests

This will add profiles used by tests (and also delete all existing profiles)

```shell
python3 tests/setup_profiles.py
```

To run a controlled test we use fakeblog123 which we control. This will import the same blog and posts each time, but the blog has multiple feeds, useful for testing identical extractions

```shell
python3 tests/add_valid_blogs.py
```

If you only want to import one of the blogs listed in the test, grab its url and run the following;

```shell
python3 tests/add_valid_blogs.py \
	--url "https://muchdogesec.github.io/fakeblog123/feeds/rss-feed-encoded.xml"
```

After adding test blogs successfully, you can use fakeblog123 to run stable tests to check all the Obstracts post features;

```shell
python3 tests/fake_blog_tests.py
```