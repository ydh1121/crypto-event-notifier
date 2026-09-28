"""Publish a check attachment only after both observations finish."""
from __future__ import annotations

import json
from pathlib import Path
import secrets


class CheckReportOutput:
    def __init__(self, path: Path):
        self.final = path.absolute()
        self.run_id = secrets.token_hex(12)
        self.directory = self.final.parent / 'reports'
        self.progress = self.directory / 'in-progress' / f'{self.final.stem}-{self.run_id}.json'

    def prepare(self):
        # Preserve previous evidence, but do not leave it at today's upload path.
        for directory in (self.directory, self.progress.parent, self.directory / 'previous'):
            if directory.is_symlink():
                raise ValueError('Report directories must not be symbolic links.')
            directory.mkdir(parents=True, exist_ok=True)
        if self.final.is_symlink():
            raise ValueError('Report output must not be a symbolic link.')
        if self.final.exists():
            if not self.final.is_file():
                raise ValueError('Report output is not a file.')
            previous = self.directory / 'previous' / f'{self.final.stem}-{self.run_id}.json'
            self.final.rename(previous)

    def publish(self):
        result = json.loads(self.progress.read_text(encoding='utf-8'))
        runtime = result.get('runtime_review', {})
        if (runtime.get('status') != 'complete' or not isinstance(runtime.get('after'), dict)
                or not result.get('review_finished_at')):
            raise ValueError('The check has not completed both observations.')
        self.progress.replace(self.final)

