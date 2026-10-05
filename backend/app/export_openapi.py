"""Write the API's OpenAPI description to a file: `python -m app.export_openapi <path>`.

The frontend generates its TypeScript types from this file, so a change to the API that breaks the
frontend fails to compile instead of failing in a user's browser. Keys are sorted, so the file only
changes when the API does. C# comparison: exporting swagger.json for NSwag.
"""

import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    target = Path(sys.argv[1])
    spec = json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    target.write_text(spec, encoding="utf-8", newline="\n")
    print(f"Wrote {target} ({len(app.openapi()['paths'])} paths)")


if __name__ == "__main__":
    main()
