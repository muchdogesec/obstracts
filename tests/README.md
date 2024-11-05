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

## Run tests

This will add profiles used by tests (and also delete all existing profiles)

```shell
python3 tests/setup_profiles.py
```

To run a controlled test we use fakeblog123 which we control

```shell
python3 tests/add_fakeblog123.py
```

This test will delete all existing blogs and add real security using the profile created by the previous script

```shell
python3 tests/add_test_security_blogs.py
```

After adding test blogs successfully, you can use fakeblog123 to run stable tests to check all the Obstracts post features;

```shell
python3 tests/fake_blog_tests.py
```