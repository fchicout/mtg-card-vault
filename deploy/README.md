# deploy

Compose stack and edge proxy (the identity provider is external). How to run, configure and upgrade it is documented once, in [`docs/05-architecture.md`](../docs/05-architecture.md) section 7 (infrastructure in 7.1, identity provider contract in 7.3, operator quickstart in 7.6). Variables are listed in [`.env.example`](.env.example).

Identity provider: create one public PKCE client per environment as described in [`docs/05-architecture.md`](../docs/05-architecture.md) section 7.7, then set `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID` and `OIDC_AUDIENCE` in `.env`.

Price refresh: the `worker` service (part of the default stack) refreshes the prices of every owned card at `PRICE_REFRESH_CRON` (UTC). Run one refresh by hand with `docker compose exec worker python -m mtgvault.worker --once` (exit code 0 = done, 1 = failed or stopped by an outage); the run's summary is one log line, `price refresh finished`. The container is healthy while its heartbeat file is fresh (`python -m mtgvault.worker --check-alive`).
