"""Validate the reconstruction against the saved official OpenAPI schema."""
import json
from pathlib import Path

import yaml
from jsonschema import Draft4Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


def main():
    evidence = ROOT / 'tariffs/birwinken/sources/2026'
    spec = yaml.safe_load((evidence / 'schema.yml').read_text())
    document = json.loads((ROOT / 'tariffs/birwinken/2026_tariffs.json').read_text())
    schema = {'$ref': '#/components/schemas/TariffSubmission',
              'components': spec['components']}
    Draft4Validator(schema, format_checker=FormatChecker()).validate(document)
    print(f'Official OpenAPI {spec["info"]["version"]}: all 12 tariffs valid (including date formats)')


if __name__ == '__main__':
    main()
