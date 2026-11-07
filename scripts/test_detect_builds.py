import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import detect_builds


class DetectBuildsTests(unittest.TestCase):
    def run_detection(self, apps, published, force=""):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apps_dir = root / "apps"
            apps_dir.mkdir()
            for app_id, suffix, version in apps:
                app_dir = apps_dir / app_id
                app_dir.mkdir()
                if suffix:
                    (app_dir / f"{app_id}{suffix}").write_text("{}")
                if version:
                    (app_dir / "VERSION").write_text(version)
            published_path = root / "published.json"
            published_path.write_text(json.dumps(published))
            output_path = root / "output"
            argv = [
                "detect_builds.py",
                "--published-apps-json", str(published_path),
                "--force-app", force,
            ]
            with (
                patch.object(detect_builds, "APPS_DIR", apps_dir),
                patch("sys.argv", argv),
                patch.dict("os.environ", {"GITHUB_OUTPUT": str(output_path)}),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                detect_builds.main()
            return dict(line.split("=", 1) for line in output_path.read_text().splitlines())

    def test_up_to_date_app_and_removed_app_directory_do_not_build(self):
        output = self.run_detection(
            [("app.current", ".yaml", "1.0"), ("app.removed", None, None)],
            {"app.current": {"version": "1.0"}},
        )
        self.assertEqual(output, {"should_build": "false", "apps": "[]"})

    def test_supported_manifests_build_when_unpublished(self):
        for suffix in (".yaml", ".yml", ".json"):
            with self.subTest(suffix=suffix):
                output = self.run_detection([("app.new", suffix, "1.0")], {})
                self.assertEqual(output["should_build"], "true")
                self.assertEqual(
                    json.loads(output["apps"]),
                    [{"app_id": "app.new", "version": "1.0"}],
                )

    def test_version_change_builds(self):
        output = self.run_detection(
            [("app.current", ".yaml", "2.0")],
            {"app.current": {"version": "1.0"}},
        )
        self.assertEqual(
            json.loads(output["apps"]),
            [{"app_id": "app.current", "version": "2.0"}],
        )

    def test_force_build_does_not_include_directories_without_manifests(self):
        for force in ("all", "*", "app.current"):
            with self.subTest(force=force):
                output = self.run_detection(
                    [("app.current", ".yaml", "1.0"), ("app.removed", None, None)],
                    {"app.current": {"version": "1.0"}},
                    force,
                )
                self.assertEqual(
                    json.loads(output["apps"]),
                    [{"app_id": "app.current", "version": "1.0"}],
                )

    def test_manifest_without_version_keeps_latest_behavior(self):
        output = self.run_detection([("app.new", ".json", None)], {})
        self.assertEqual(
            json.loads(output["apps"]),
            [{"app_id": "app.new", "version": "latest"}],
        )


if __name__ == "__main__":
    unittest.main()
