"""Regression: flow input must reach the review artifact in all three modes."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else Path(__file__).resolve().parent.parent
FLOWS = '# 流程图\n\n入口：用户提交；校验失败保留输入；成功生成结果。\n\n```mermaid\ngraph TD\n A[提交] --> B{通过?}\n B -->|是| C[完成]\n B -->|否| A\n```\n'


class BuildFlows(unittest.TestCase):
    def test_flow_input_survives_all_modes(self):
        for mode in ['generate', 'enhance', 'assemble']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / 'flows.md').write_text(FLOWS)
                (root / 'prd.md').write_text('# 测试项目\n\n## 业务规则\n提交通过才生成结果。')
                ann = [{'id': 'submit', 'order': 1, 'pageId': 'home', 'title': '提交', 'body': '点击提交', 'businessRules': [], 'scope': {'type': 'page', 'id': 'home'}}]
                (root / 'annotations.json').write_text(json.dumps(ann))
                plain = '<!doctype html><html><body><button data-anno="submit" onclick="this.textContent=\'完成\'">提交</button></body></html>'
                (root / 'prototype.html').write_text(plain)
                inputs = {'flows': 'flows.md'}
                if mode == 'generate':
                    inputs['product_model'] = str(SKILL / 'assets/product-model-template.json')
                else:
                    inputs.update(prd='prd.md', prototype='prototype.html', annotations='annotations.json')
                    if mode == 'assemble':
                        prepared = subprocess.run([sys.executable, str(SKILL / 'scripts/prepare-prototype.py'), str(root / 'prototype.html'), '--annotations', str(root / 'annotations.json'), '--page-id', 'home', '--output', str(root / 'prepared.html')], capture_output=True, text=True)
                        self.assertEqual(prepared.returncode, 0, prepared.stderr)
                        inputs['prototype'] = 'prepared.html'
                manifest = {'schema_version': '1.0', 'mode': mode, 'output_dir': 'dist', 'inputs': inputs}
                (root / 'project.json').write_text(json.dumps(manifest))
                built = subprocess.run([sys.executable, str(SKILL / 'scripts/build-review.py'), str(root / 'project.json')], capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
                html = (root / 'dist/visual-prd.html').read_text()
                payload = re.search(r'const FLOWS_PAYLOAD = "([^"]*)"', html)
                self.assertIsNotNone(payload, 'Flow input was dropped from review artifact')
                self.assertEqual(base64.b64decode(payload[1]).decode(), FLOWS)
                self.assertEqual((root / 'dist/flows.md').read_text(), FLOWS)


if __name__ == '__main__':
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    unittest.main()
