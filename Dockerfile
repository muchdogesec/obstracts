FROM python:3.11
ENV PYTHONUNBUFFERED=1

WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . /usr/src/app
RUN pip install --no-deps --force-reinstall ./dogesec_commons-0.0.1b2-py3-none-any.whl