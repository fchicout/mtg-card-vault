# MTG Card Vault

A self-hosted, multi-user web application in which *Magic: The Gathering* collectors keep a private, priced inventory of their cards, adding cards by showing them to a webcam. Angular + Clarity front end, FastAPI back end, PostgreSQL, Authelia sign-in, Scryfall for card data and prices.

**Status:** early development (milestone M0, foundations). Nothing here is a release yet; see the milestones in [`docs/01-project-charter.md`](docs/01-project-charter.md) section 10.

## Where to read

Everything about what the product is, why, how it behaves and how it is built lives in the synchronized documentation set: start at [`docs/README.md`](docs/README.md). This file only points there so that nothing is stated twice.

- Contributing (branches, commits, quality gates, releases): [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Reporting a vulnerability: [`SECURITY.md`](SECURITY.md)
- Code of conduct: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)

## Quickstart

A first working stack arrives with issue #10; until then:

```bash
make gates                      # every quality gate that runs without containers
make docs-check                 # the documentation set is synchronized
deploy/authelia/dev-secrets.sh && cp -n deploy/.env.example deploy/.env   # then set POSTGRES_PASSWORD in deploy/.env
docker compose -f deploy/compose.yaml --profile ci up -d authelia && python3 deploy/authelia/roundtrip.py   # dev identity provider
```

## Licence

[MIT](LICENSE).

## Legal notice

MTG Card Vault is unofficial Fan Content permitted under the Wizards of the Coast Fan Content Policy. It is not approved or endorsed by Wizards of the Coast. *Magic: The Gathering* is a trademark of Wizards of the Coast LLC. Card data and images are provided by [Scryfall](https://scryfall.com), which is not affiliated with this project.
