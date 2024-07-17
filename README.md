# Obstracts

## Overview

Obstracts takes a blog ATOM or RSS feed and converts into structured threat intelligence.

Organisations subscribe to lots of blogs for security information. These blogs contain interesting indicators of malicious activity (e.g. malicious URL).

To help automate the extraction of this information, Obstracts automatically downloads blog articles and extracts indicators for viewing to a user.

It works at a high level like so:

1. A feed is added to Obstracts by user (selecting profile to be used)
2. Obstracts uses history4feed as a microservice to handle the download and storage of posts.
3. The HTML from history4feed for each blog post is converted to markdown using file2txt in `html` mode
4. The markdown is run through txt2stix where txt2stix pattern extractions/whitelists/aliases are run based on staff defined profile
5. STIX bundles are generated for each post of the blog, and stored in a collection called `obstracts`
6. A user can access the bundle data or specific objects in the bundle via the API
7. As new posts are added to remote blogs, user makes request to update blog and these are requested by history4feed

### Download and configure

```shell
# clone the latest code
git clone https://github.com/muchdogesec/obstracts
```

### Configuration options

Obstracts has various settings that are defined in an `.env` file.

To create one using the default settings:

```shell
cp .env.example .env
```

### Build the Docker Image

```shell
sudo docker-compose build
```

### Start the server

```shell
sudo docker-compose up
```


## Useful supporting tools

* [An up-to-date list of threat intel blogs that post cyber threat intelligence research](https://github.com/muchdogesec/awesome_threat_intel_blogs)

## Support

[Minimal support provided via the DOGESEC community](https://community.dogesec.com/).

## License

[AGPLv3](/LICENSE).