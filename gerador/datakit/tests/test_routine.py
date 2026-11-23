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


def _stale(source, copy_date, days, reason="download falhou (ConnectTimeout)"):
    return {"source": source, "copy_date": copy_date, "days": days, "reason": reason}


class StaleSources(unittest.TestCase):
    """Fonte parada: o campo `stale` do catálogo do build vira a lista do alerta."""
    BUILT_AT = "2026-11-22T06:30:00Z"

    def _catalog(self, *entries):
        return {"built_at": self.BUILT_AT, "stale": [
            {"source": s, "copy_date": d, "reason": r} for s, d, r in entries]}

    def test_only_copies_of_three_days_or_more_count_and_the_oldest_comes_first(self):
        cat = self._catalog(("OSM sul", "2026-11-19", "baixar a versão nova falhou (HTTPError)"),   # 3 dias
                            ("Inmetro GO", "2026-11-21", "download falhou"),                         # 1
                            ("EPTC (radares)", "2026-11-20", "Power BI falhou"),                     # 2
                            ("CET-SP (radares)", "2026-11-10", "Power BI e CSV falharam"))           # 12
        found = rt.stale_sources(cat)
        self.assertEqual([(e["source"], e["days"]) for e in found], [("CET-SP (radares)", 12), ("OSM sul", 3)])
        self.assertEqual(found[1], {"source": "OSM sul", "copy_date": "2026-11-19", "days": 3,
                                    "reason": "baixar a versão nova falhou (HTTPError)"})

    def test_the_limit_is_three_days(self):
        self.assertEqual(rt.STALE_DAYS, 3)

    def test_no_field_or_unreadable_entries_give_nothing(self):
        self.assertEqual(rt.stale_sources({"built_at": self.BUILT_AT}), [])
        self.assertEqual(rt.stale_sources(self._catalog(("X", "ontem", ""), ("Y", "", ""))), [])
        self.assertEqual(rt.stale_sources({"built_at": self.BUILT_AT, "stale": [{"copy_date": "2026-11-01"}, "x"]}), [])

    def test_the_command_prints_compact_json_and_survives_a_missing_catalog(self):
        import contextlib
        import io
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "catalogo.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._catalog(("OSM sul", "2026-11-18", "x")), f)
            for catalog, expected in ((path, [_stale("OSM sul", "2026-11-18", 4, "x")]),
                                      (os.path.join(tmp, "nao-existe.json"), [])):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(rt.main(["stale", "--catalog", catalog]), 0)
                self.assertEqual(json.loads(out.getvalue()), expected)
                self.assertEqual(len(out.getvalue().strip().splitlines()), 1)


class NotifyStale(unittest.TestCase):
    URL = "https://github.com/x/y/actions/runs/1"
    NOW = utc("2026-11-22T06:30:00")
    PARADA = [_stale("OSM sul", "2026-11-19", 3, "baixar a versão nova falhou (HTTPError)")]

    def _open(self):
        return FakeGh({("issue", "list"): json.dumps([{"number": 7, "title": rt.ISSUE_TITLE}])})

    def test_a_source_stopped_for_three_days_opens_the_issue_even_if_the_job_is_green(self):
        gh = FakeGh({("issue", "list"): "[]"})
        self.assertEqual(rt.notify("x/y", False, self.URL, self.NOW, gh, stale=self.PARADA), "opened")
        create = [c for c in gh.calls if c[:2] == ["issue", "create"]][0]
        body = create[create.index("--body") + 1]
        self.assertIn(rt.ISSUE_TITLE, create)
        self.assertIn("22/11/2026 03:30", body)
        self.assertIn("- OSM sul: cópia de 2026-11-19 (3 dias) — baixar a versão nova falhou (HTTPError)", body)
        self.assertIn(self.URL, body)

    def test_it_comments_if_the_issue_is_already_open(self):
        gh = self._open()
        self.assertEqual(rt.notify("x/y", False, self.URL, self.NOW, gh, stale=self.PARADA), "commented")
        self.assertEqual(gh.calls[-1][:3], ["issue", "comment", "7"])
        self.assertIn("OSM sul", gh.calls[-1][gh.calls[-1].index("--body") + 1])
        self.assertFalse([c for c in gh.calls if c[:2] in (["issue", "close"], ["issue", "create"])])

    def test_copies_of_one_or_two_days_do_nothing(self):
        recent = [_stale("Inmetro GO", "2026-11-21", 1), _stale("EPTC (radares)", "2026-11-20", 2)]
        gh = FakeGh({("issue", "list"): "[]"})
        self.assertEqual(rt.notify("x/y", False, self.URL, self.NOW, gh, stale=recent), "nothing")
        self.assertEqual([c[:2] for c in gh.calls], [["issue", "list"]])
        # com a issue aberta, cópia recente conta como normal: fecha
        gh = self._open()
        self.assertEqual(rt.notify("x/y", False, self.URL, self.NOW, gh, stale=recent), "closed")

    def test_it_closes_when_there_is_no_failure_and_no_stopped_source(self):
        gh = self._open()
        self.assertEqual(rt.notify("x/y", False, self.URL, self.NOW, gh, stale=[]), "closed")
        self.assertEqual(gh.calls[-1], ["issue", "close", "7", "--repo", "x/y"])
        self.assertIn("sem fonte parada", gh.calls[-2][gh.calls[-2].index("--body") + 1])

    def test_a_stopped_source_keeps_the_issue_open(self):
        gh = self._open()
        rt.notify("x/y", False, self.URL, self.NOW, gh, stale=self.PARADA)
        self.assertFalse([c for c in gh.calls if c[:2] == ["issue", "close"]])

    def test_a_failed_job_still_opens_and_lists_the_sources_too(self):
        gh = FakeGh({("issue", "list"): "[]"})
        self.assertEqual(rt.notify("x/y", True, self.URL, self.NOW, gh), "opened")
        body = gh.calls[-1][gh.calls[-1].index("--body") + 1]
        self.assertIn("falhou", body)
        self.assertNotIn("Fontes que usaram", body)
        gh = FakeGh({("issue", "list"): "[]"})
        self.assertEqual(rt.notify("x/y", True, self.URL, self.NOW, gh, stale=self.PARADA), "opened")
        body = gh.calls[-1][gh.calls[-1].index("--body") + 1]
        self.assertIn("falhou", body)
        self.assertIn("OSM sul", body)

    def test_the_command_takes_the_json_of_the_stale_command(self):
        import contextlib
        import io
        from unittest import mock
        calls = []

        def fake_notify(*args, **kw):
            calls.append((args, kw))
            return "opened"
        with mock.patch.object(rt, "notify", fake_notify), contextlib.redirect_stdout(io.StringIO()):
            rt.main(["notify", "--repo", "x/y", "--run-url", self.URL, "--stale", json.dumps(self.PARADA)])
            rt.main(["notify", "--repo", "x/y", "--run-url", self.URL, "--stale", "isto não é json"])
            rt.main(["notify", "--repo", "x/y", "--run-url", self.URL])
        self.assertEqual([kw["stale"] for _, kw in calls], [self.PARADA, [], []])


class WorkflowWiring(unittest.TestCase):
    """O notify só tem o script: a lista de fontes paradas passa pela saída do job generate."""
    PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".github", "workflows", "gerar-dados.yml")

    def setUp(self):
        with open(self.PATH, encoding="utf-8") as f:
            self.text = f.read()

    def test_generate_exposes_the_list_read_from_the_build_catalog(self):
        generate = self.text.split("\n  generate:\n", 1)[1].split("\n  notify:\n", 1)[0]
        self.assertIn("stale: ${{ steps.stale.outputs.stale }}", generate)
        self.assertIn("routine.py stale --catalog data/dist/catalogo.json", generate)
        self.assertIn("id: stale", generate)

    def test_notify_hands_it_to_both_calls(self):
        notify = self.text.split("\n  notify:\n", 1)[1]
        self.assertIn("STALE: ${{ needs.generate.outputs.stale }}", notify)
        self.assertEqual(notify.count('--stale "${STALE:-[]}"'), 2)
        self.assertIn("github.event_name == 'schedule'", notify)   # disparo à mão não mexe na issue


if __name__ == "__main__":
    unittest.main()
