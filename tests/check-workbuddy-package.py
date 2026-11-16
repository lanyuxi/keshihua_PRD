#!/usr/bin/env python3
"""Check the actual upload artifact against the reported publishing contract."""
import importlib.util
import re
import sys
import tempfile
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent / 'visual-prd'
FIELDS = ('version', 'display_name', 'display_name_en', 'description_zh', 'description_en')


def frontmatter(source):
    match = re.match(r'^---\n(.*?)\n---\n', source, re.S)
    assert match, 'Missing YAML frontmatter'
    return yaml.safe_load(match.group(1)), source[match.end():]


def main():
    archive = Path(sys.argv[1])
    canonical = (ROOT / 'SKILL.md').read_text()
    expected, body = frontmatter(canonical)
    with zipfile.ZipFile(archive) as package:
        assert package.testzip() is None
        actual_source = package.read('SKILL.md').decode('utf-8')
        actual, actual_body = frontmatter(actual_source)
        missing = [key for key in FIELDS if not isinstance(actual.get(key), str) or not actual[key].strip()]
        assert not missing, f'Missing WorkBuddy top-level fields: {missing}'
        assert actual['version'] == expected['metadata']['version']
        assert actual['display_name'] == '可视化 PRD'
        assert actual['display_name_en'] == 'Visual PRD'
        assert actual['description_zh'] == expected['description']
        assert actual['description_en'] == expected['metadata']['description_en']
        assert actual_body == body, 'Skill instructions changed during packaging'
        for member in package.namelist():
            if member != 'SKILL.md':
                assert package.read(member) == (ROOT / member).read_bytes(), member
        total = sum(item.file_size for item in package.infolist())
        assert total <= 3_145_728, total
        assert archive.stat().st_size < 3_000_000

    sys.path.insert(0, str(ROOT / 'scripts'))
    spec = importlib.util.spec_from_file_location('package_validator', ROOT / 'scripts/validate-package.py')
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    with tempfile.TemporaryDirectory() as temporary:
        test_root = Path(temporary)
        validator.SKILL_ROOT = test_root
        # Broken metadata must fail before reference/build checks.
        broken = {
            'missing English description': re.sub(r'^  description_en:.*\n', '', canonical, flags=re.M),
            'nested version cannot hide bad top-level version': actual_source.replace("version: \"" + actual['version'] + '"', 'version: "invalid"', 1),
            'missing publishing field': re.sub(r'^display_name_en:.*\n', '', actual_source, flags=re.M),
        }
        for label, source in broken.items():
            (test_root / 'SKILL.md').write_text(source)
            try:
                validator.validate_frontmatter()
            except ValueError as error:
                assert 'reference' not in str(error).lower(), (label, str(error))
            else:
                raise AssertionError(f'Accepted {label}')
    print(f'PASS WorkBuddy fields, payload preservation, negative checks; expanded bytes: {total}')


if __name__ == '__main__':
    main()
