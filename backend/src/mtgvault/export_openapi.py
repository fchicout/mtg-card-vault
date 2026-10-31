"""Write the OpenAPI document to a file (FR-API-01). The Angular client is generated from it.

Usage: ``python -m mtgvault.export_openapi openapi.json``
"""

import json
import sys
from pathlib import Path

from mtgvault.main import create_app


class _NeverReady:
    """Stand-in probe so exporting the contract needs no database."""

    def is_ready(self) -> bool:
        return False


def build_document() -> str:
    schema = create_app(readiness_probe=_NeverReady()).openapi()
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: python -m mtgvault.export_openapi <output-file>\n")
        return 2
    Path(argv[1]).write_text(build_document(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
