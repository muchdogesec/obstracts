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

```shell
python3 tests/add_test_blogs.py
```

After adding test blogs, the following 

feed 2d6575b8-3d90-5479-bdfe-b980b753ec40
post c6a5afcd-2341-5a57-b936-b9a67667f57e

