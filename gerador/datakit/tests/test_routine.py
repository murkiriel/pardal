"""Rotina da geração (scripts/routine.py): commit semanal com nova tentativa, limpeza das releases e
issue de falha, com um gh falso."""
import importlib.util
import json
import os
import unittest
from datetime import datetime, timezone

_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "routine.py"))
_spec = importlib.util.spec_from_file_location("routine", _PATH)
assert _spec is not None and _spec.loader is not None
rt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rt)


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


class FakeGh:
    def __init__(self, answers=None):
        self.calls = []
        self.answers = answers or {}

    def __call__(self, args):
        self.calls.append(list(args))
        for prefix, out in self.answers.items():
            if list(args[:len(prefix)]) == list(prefix):
                return out
        return ""


class Mode(unittest.TestCase):
    def test_week_starts_on_sunday_midnight_in_brasilia(self):
        # domingo 08/11/2026 00:00 em Brasília = 03:00 UTC
        self.assertEqual(rt.week_start(utc("2026-11-08T06:17:00")), utc("2026-11-08T03:00:00"))
        self.assertEqual(rt.week_start(utc("2026-11-11T12:00:00")), utc("2026-11-08T03:00:00"))   # quarta
        self.assertEqual(rt.week_start(utc("2026-11-08T02:00:00")), utc("2026-11-01T03:00:00"))   # sábado à noite em Brasília

    def test_sunday_commits_when_the_repository_is_from_last_week(self):
        self.assertEqual(rt.mode("2026-11-01T06:50:00Z", "schedule", True, utc("2026-11-08T06:17:00")), "commit")

    def test_second_sunday_trigger_after_a_commit_only_releases(self):
        self.assertEqual(rt.mode("2026-11-08T07:00:00Z", "schedule", True, utc("2026-11-08T12:17:00")), "release")

    def test_failed_sunday_is_retried_on_monday(self):
        self.assertEqual(rt.mode("2026-11-01T06:50:00Z", "schedule", True, utc("2026-11-09T06:17:00")), "commit")

    def test_weekdays_after_the_weekly_commit_only_release(self):
        self.assertEqual(rt.mode("2026-11-08T07:00:00Z", "schedule", True, utc("2026-11-12T06:17:00")), "release")

    def test_manual_publish_always_commits_and_without_publish_nothing(self):
        self.assertEqual(rt.mode("2026-11-08T07:00:00Z", "workflow_dispatch", True, utc("2026-11-10T15:00:00")), "commit")
        self.assertEqual(rt.mode("2026-11-01T07:00:00Z", "workflow_dispatch", False, utc("2026-11-10T15:00:00")), "none")
        self.assertEqual(rt.mode(None, "schedule", True, utc("2026-11-10T06:17:00")), "commit")


class Prune(unittest.TestCase):
    def _gh(self, releases):
        return FakeGh({("api",): json.dumps([releases])})

    def test_old_daily_releases_go_weekly_and_recent_stay(self):
        now = utc("2027-03-01T07:00:00")
        rels = [
            {"tag_name": "dados-2026-10-06", "created_at": "2026-10-06T13:44:14Z", "body": "... no commit desta versão."},
            {"tag_name": "dados-2026-11-09", "created_at": "2026-11-09T07:00:00Z", "body": "Estes dados estão só nesta release"},
            {"tag_name": "dados-2026-11-10-1530", "created_at": "2026-11-10T15:30:00Z", "body": ""},
            {"tag_name": "dados-2027-02-20", "created_at": "2027-02-20T07:00:00Z", "body": "só nesta release"},
            {"tag_name": "v1.0", "created_at": "2026-01-01T00:00:00Z", "body": ""},
        ]
        gh = self._gh(rels)
        gone = rt.prune("x/y", now, gh)
        self.assertEqual(gone, ["dados-2026-11-09", "dados-2026-11-10-1530"])
        self.assertIn(["release", "delete", "dados-2026-11-09", "--repo", "x/y", "--yes", "--cleanup-tag"], gh.calls)

    def test_the_newest_release_is_never_deleted(self):
        rels = [{"tag_name": "dados-2026-01-01", "created_at": "2026-01-01T07:00:00Z", "body": ""}]
        self.assertEqual(rt.prune("x/y", utc("2027-01-01T00:00:00"), self._gh(rels)), [])


class Notify(unittest.TestCase):
    URL = "https://github.com/x/y/actions/runs/1"

    def test_first_failure_opens_the_issue(self):
        gh = FakeGh({("issue", "list"): "[]"})
        self.assertEqual(rt.notify("x/y", True, self.URL, utc("2026-11-09T06:30:00"), gh), "opened")
        create = [c for c in gh.calls if c[:2] == ["issue", "create"]][0]
        self.assertIn(rt.ISSUE_TITLE, create)
        self.assertIn("09/11/2026 03:30", create[create.index("--body") + 1])

    def test_next_failure_comments_on_the_open_issue(self):
        gh = FakeGh({("issue", "list"): json.dumps([{"number": 7, "title": rt.ISSUE_TITLE}])})
        self.assertEqual(rt.notify("x/y", True, self.URL, utc("2026-11-10T06:30:00"), gh), "commented")
        self.assertEqual(gh.calls[-1][:3], ["issue", "comment", "7"])

    def test_success_closes_it_and_without_issue_does_nothing(self):
        gh = FakeGh({("issue", "list"): json.dumps([{"number": 7, "title": rt.ISSUE_TITLE}])})
        self.assertEqual(rt.notify("x/y", False, self.URL, utc("2026-11-11T06:30:00"), gh), "closed")
        self.assertEqual(gh.calls[-1], ["issue", "close", "7", "--repo", "x/y"])
        self.assertEqual(rt.notify("x/y", False, self.URL, utc("2026-11-11T06:30:00"), FakeGh({("issue", "list"): "[]"})),
                         "nothing")

    def test_an_issue_with_a_similar_title_is_not_ours(self):
        gh = FakeGh({("issue", "list"): json.dumps([{"number": 3, "title": "Geração falhando no fork"}])})
        self.assertEqual(rt.notify("x/y", True, self.URL, utc("2026-11-09T06:30:00"), gh), "opened")


if __name__ == "__main__":
    unittest.main()
