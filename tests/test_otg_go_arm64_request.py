"""执行 workflow 中真实的请求校验器，保护 tag 与上游验证边界。"""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / '.github/workflows/otg-go-arm64.yml').read_text()
VALIDATOR = textwrap.dedent(SOURCE.split("python3 - <<'PYCODE'\n", 1)[1].split('          PYCODE', 1)[0])
SHA = 'a' * 40

class RequestTests(unittest.TestCase):
    def validate(self, event='push', head_sha=SHA, head_branch='2.3.14', tag_sha=SHA,
                 attempt=1, missing='', conclusion='success', annotated=False):
        payload = dict(request_id='b'*32, source_sha=SHA, version='2.3.14',
                       upstream_run_id='123', upstream_run_attempt='1')
        names = ['Build standard payload', 'Build kylin-xc payload',
                 'Release QA / Full QA', 'Release QA / QA']
        names += [f'Debian {kind} ({suite})' for kind in ('runtime', 'lifecycle')
                  for suite in ('buster', 'bullseye', 'bookworm', 'trixie')]
        jobs = [dict(name=name, status='completed', conclusion=conclusion)
                for name in names if name != missing]
        run = dict(path='.github/workflows/release-payload.yml', event=event,
                   head_sha=head_sha, head_branch=head_branch, run_attempt=attempt)
        calls = []
        def response(request, timeout):
            calls.append(request.full_url)
            if '/git/ref/tags/' in request.full_url:
                obj = dict(type='tag' if annotated else 'commit', sha='c'*40 if annotated else tag_sha)
                value = dict(object=obj)
            elif '/git/tags/' in request.full_url:
                value = dict(object=dict(type='commit', sha=tag_sha))
            elif '/jobs?' in request.full_url:
                value = dict(jobs=copy.deepcopy(jobs))
            else:
                value = copy.deepcopy(run)
            return io.BytesIO(json.dumps(value).encode())
        with tempfile.TemporaryDirectory() as temporary:
            event_path, output = Path(temporary)/'event.json', Path(temporary)/'output'
            event_path.write_text(json.dumps(dict(client_payload=payload)))
            with patch.dict(os.environ, dict(GITHUB_EVENT_PATH=str(event_path),
                                            GITHUB_OUTPUT=str(output), GH_TOKEN='fixture-token')), \
                 patch('urllib.request.urlopen', side_effect=response):
                exec(compile(VALIDATOR, 'workflow-request-validator', 'exec'), {})
            self.assertIn('source_event=push', output.read_text())
        return calls

    def test_valid_lightweight_and_annotated_tags(self):
        self.assertEqual(len(self.validate()), 3)
        self.assertEqual(len(self.validate(annotated=True)), 4)

    def test_non_tag_and_mismatched_identity_are_rejected(self):
        for changes in (dict(event='pull_request_target'), dict(event='workflow_dispatch'),
                        dict(head_branch='master'), dict(head_sha='d'*40),
                        dict(tag_sha='d'*40), dict(attempt=2)):
            with self.subTest(changes=changes), self.assertRaises(SystemExit):
                self.validate(**changes)

    def test_every_upstream_validation_must_actually_pass(self):
        for name in ('Build standard payload', 'Build kylin-xc payload',
                     'Release QA / Full QA', 'Release QA / QA',
                     'Debian runtime (buster)', 'Debian lifecycle (trixie)'):
            with self.subTest(name=name), self.assertRaises(SystemExit):
                self.validate(missing=name)
        for conclusion in ('failure', 'cancelled', 'skipped'):
            with self.subTest(conclusion=conclusion), self.assertRaises(SystemExit):
                self.validate(conclusion=conclusion)

if __name__ == '__main__':
    unittest.main()
