# fastapi
Testing with FastAPI

Prerequisites

```
export FAST_PASSWORD=xxxxxx
export FAST_USERNAME=xxxxxx
export FAST_HOSTNAME=xxxxxx
export FAST_PLATFORM=xxxxxx
export VOUCH_COOKIE_DOMAIN=example.com
export OAUTH_PROVIDER=xxxxxx
export OAUTH_CLIENT_ID=xxxxxx
export OAUTH_CLIENT_SECRET=xxxxxx
export CERTBOT_DOMAIN=app.example.com
export CERTBOT_EMAIL=xxxxxx

cd fastapi
sudo docker-compose up
```

Start FastAPI

```
pip3 install pipenv
pipenv shell
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
