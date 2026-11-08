from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MusicSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.binary = str(Path(cls.tmp.name) / 'music-sync-tests')
        subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                        str(ROOT / 'tests/music_sync.cpp'), '-o', cls.binary], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, name):
        subprocess.run([self.binary, name], check=True)

    def test_twenty_minutes_level_ahead(self): self.run_case('long-ahead')
    def test_twenty_minutes_song_ahead(self): self.run_case('long-behind')
    def test_no_changes_without_drift(self): self.run_case('no-drift')
    def test_variable_refresh_and_late_frames(self): self.run_case('variable-fps')
    def test_initial_song_offset(self): self.run_case('offset')
    def test_transient_stale_reading(self): self.run_case('transient')
    def test_alternating_reading_jitter(self): self.run_case('alternating-jitter')
    def test_asynchronous_seek_and_cooldown(self): self.run_case('cooldown')
    def test_retries_and_checkpoint_baselines(self): self.run_case('restart')
    def test_manual_seeks_and_loops(self): self.run_case('manual-seek')
    def test_invalid_and_discontinuous_clocks(self): self.run_case('invalid')
    def test_suspend_and_wall_clock_changes(self): self.run_case('suspension')
