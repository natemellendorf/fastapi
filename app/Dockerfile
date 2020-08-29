FROM python:3.8.3-alpine3.10

COPY ./ /app

WORKDIR /app

RUN apk update \
 && apk add --no-cache \
 build-base \
 libxml2-dev \
 libxslt-dev \
 python3-dev \
 gcc \
 openssl-dev \
 musl-dev \
 libffi-dev \
 ca-certificates \
 && update-ca-certificates

RUN /usr/local/bin/python -m pip install --upgrade pip

RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT python3 main.py
