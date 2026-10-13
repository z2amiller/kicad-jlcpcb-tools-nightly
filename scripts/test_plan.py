"""Unit tests for plan.py: python3 -m unittest discover -s scripts -v"""

import json
import unittest

import plan


def release(tag, *, exe=True, dmg=True, draft=False, prerelease=False):
    """Build a release as the GitHub API returns it, with chosen installers."""
    windows, macos = plan.installer_names(tag)
    names = ["kicad-" + tag + "-arm64.exe"]
    if exe:
        names.append(windows)
    if dmg:
        names.append(macos)
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "assets": [{"name": name} for name in names],
    }


BASE = [release("7.0.11"), release("8.0.9"), release("9.0.8"), release("10.0.5")]

SHA_MAIN = "1" * 40
SHA_TAG_OBJECT = "2" * 40
SHA_TAGGED_COMMIT = "3" * 40
SHA_LIGHT_TAG = "4" * 40


class PickVersionsTest(unittest.TestCase):
    def test_fixed_releases_then_newest_of_each_later_series(self):
        releases = BASE + [release("9.0.9"), release("10.0.6"), release("10.0.4")]
        self.assertEqual(
            plan.pick_versions(releases), ["7.0.11", "8.0.9", "9.0.9", "10.0.6"]
        )

    def test_patch_numbers_compare_as_numbers(self):
        releases = BASE + [release("9.0.9"), release("9.0.10")]
        self.assertEqual(plan.pick_versions(releases)[2], "9.0.10")

    def test_a_release_still_uploading_its_installers_is_passed_over(self):
        releases = BASE + [release("10.0.6"), release("10.0.7", dmg=False)]
        self.assertEqual(plan.pick_versions(releases)[3], "10.0.6")
        releases = BASE + [release("10.0.6"), release("10.0.7", exe=False)]
        self.assertEqual(plan.pick_versions(releases)[3], "10.0.6")

    def test_drafts_prereleases_and_rc_tags_are_passed_over(self):
        releases = BASE + [
            release("10.0.7", draft=True),
            release("10.0.8", prerelease=True),
            release("10.0.9-rc1"),
            release("10.99"),
        ]
        self.assertEqual(plan.pick_versions(releases)[3], "10.0.5")

    def test_a_fixed_release_without_installers_stops_the_plan(self):
        releases = [release("7.0.11", exe=False), *BASE[1:]]
        with self.assertRaisesRegex(plan.PlanError, "7.0.11"):
            plan.pick_versions(releases)

    def test_a_series_with_no_complete_release_stops_the_plan(self):
        releases = [*BASE[:3], release("10.0.5", dmg=False)]
        with self.assertRaisesRegex(plan.PlanError, r"10\.0\.x"):
            plan.pick_versions(releases)


class ResolveShaTest(unittest.TestCase):
    LS_REMOTE = (
        f"{SHA_MAIN}\trefs/heads/main\n"
        f"{SHA_TAG_OBJECT}\trefs/tags/v1\n"
        f"{SHA_TAGGED_COMMIT}\trefs/tags/v1^{{}}\n"
        f"{SHA_LIGHT_TAG}\trefs/tags/light\n"
        f"{SHA_LIGHT_TAG}\trefs/tags/main\n"
    )

    def test_a_branch_resolves_to_its_head(self):
        self.assertEqual(plan.resolve_sha(self.LS_REMOTE, "main"), SHA_MAIN)

    def test_an_annotated_tag_resolves_to_its_commit_not_the_tag_object(self):
        self.assertEqual(plan.resolve_sha(self.LS_REMOTE, "v1"), SHA_TAGGED_COMMIT)

    def test_a_lightweight_tag_resolves_to_its_commit(self):
        self.assertEqual(plan.resolve_sha(self.LS_REMOTE, "light"), SHA_LIGHT_TAG)

    def test_a_full_sha_is_taken_as_is_in_lower_case(self):
        self.assertEqual(plan.resolve_sha("", "ABCDEF" + "0" * 34), "abcdef" + "0" * 34)

    def test_ls_remote_is_asked_for_the_peeled_tag_by_name(self):
        # git ls-remote omits `refs/tags/v1^{}` unless that exact name is a pattern.
        self.assertEqual(
            plan.remote_patterns("v1"),
            ["refs/heads/v1", "refs/tags/v1", "refs/tags/v1^{}"],
        )

    def test_a_short_sha_or_unknown_ref_names_the_fix(self):
        for ref in ("1234567", "no-such-branch"):
            with self.assertRaisesRegex(plan.PlanError, "full 40-character SHA"):
                plan.resolve_sha(self.LS_REMOTE, ref)


class TargetTest(unittest.TestCase):
    def test_a_scheduled_run_tests_bouni_main(self):
        self.assertEqual(
            plan.target({"TARGET_REPOSITORY": "", "TARGET_REF": ""}),
            ("Bouni/kicad-jlcpcb-tools", "main"),
        )
        self.assertEqual(plan.target({}), ("Bouni/kicad-jlcpcb-tools", "main"))

    def test_a_manual_run_tests_what_it_names(self):
        self.assertEqual(
            plan.target(
                {
                    "TARGET_REPOSITORY": " z2amiller/kicad-jlcpcb-tools ",
                    "TARGET_REF": "fix/x",
                }
            ),
            ("z2amiller/kicad-jlcpcb-tools", "fix/x"),
        )

    def test_a_repository_that_is_not_owner_slash_name_stops_the_plan(self):
        for repository in ("kicad-jlcpcb-tools", "https://github.com/a/b", "a/b c"):
            with self.assertRaises(plan.PlanError):
                plan.target({"TARGET_REPOSITORY": repository})


class MatrixAndKeyTest(unittest.TestCase):
    VERSIONS = ["7.0.11", "8.0.9", "9.0.9", "10.0.6"]

    def test_one_lane_per_runner_per_kicad(self):
        lanes = plan.build_matrix(self.VERSIONS)["include"]
        self.assertEqual(len(lanes), 8)
        self.assertIn(
            {
                "os": "windows-latest",
                "label": "Windows",
                "kicad": "10.0.6",
                "major": "10",
            },
            lanes,
        )
        self.assertIn(
            {"os": "macos-latest", "label": "macOS", "kicad": "7.0.11", "major": "7"},
            lanes,
        )
        json.dumps(lanes)  # the workflow reads it with fromJSON

    def test_the_key_names_the_commit_and_every_kicad(self):
        self.assertEqual(
            plan.cache_key(SHA_MAIN, self.VERSIONS),
            f"tested-{SHA_MAIN}-7.0.11-8.0.9-9.0.9-10.0.6",
        )


if __name__ == "__main__":
    unittest.main()
