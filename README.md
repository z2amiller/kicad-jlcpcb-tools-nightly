# kicad-jlcpcb-tools nightly

Runs the native KiCad tests of
[kicad-jlcpcb-tools](https://github.com/Bouni/kicad-jlcpcb-tools) on Windows
and macOS, inside each KiCad's own Python and wxPython: the runtimes the
plugin's users have. The project's own CI runs on Linux, with Ubuntu's Python
and wxGTK, so it cannot see problems that only these bundles show.

## What it runs

| | Windows (`windows-latest`) | macOS (`macos-latest`) |
| --- | --- | --- |
| KiCad 7.0.11 | Python 3.9, msw wx 3.2 | Python 3.9, Cocoa wx 3.2 |
| KiCad 8.0.9 | Python 3.11, msw wx 3.2 | Python 3.9, Cocoa wx 3.2 |
| newest 9.0.x | Python 3.11, msw wx 3.2 | Python 3.9, Cocoa wx 3.2 |
| newest 10.0.x | Python 3.11, msw wx 3.3 | Python 3.9, Cocoa wx 3.2 |

Each lane:

1. installs KiCad from its release on
   [KiCad/kicad-source-mirror](https://github.com/KiCad/kicad-source-mirror/releases),
   with the silent installer on Windows (into `C:\Program Files\KiCad`) and
   from the disk image on macOS;
2. installs pytest into KiCad's bundled Python;
3. runs
   `pytest -rs --require-native=kicad --kicad-major=<N> -m native_kicad tests`
   in the plugin's checkout.

A lane takes two to three minutes. The newest 9.0.x and 10.0.x are looked up
at the start of every run; a release counts once both its Windows and macOS
installers are uploaded.

## When it runs

The scheduled run tests `Bouni/kicad-jlcpcb-tools` `main` once a night. It
skips the lanes when the same commit was already tested on the same KiCad
builds, whether that run passed or failed, so a failure is reported once per
change. The record lasts until the end of the ISO week, so a quiet week is
re-tested once, which also catches changes to the runners themselves.

## Running it on a branch

Start the workflow by hand from the Actions tab, or with the GitHub CLI:

```sh
gh workflow run nightly.yml -R z2amiller/kicad-jlcpcb-tools-nightly \
  -f repository=z2amiller/kicad-jlcpcb-tools -f ref=my-branch
```

`ref` takes a branch, a tag or a full 40-character commit SHA. A manual run
always runs the lanes, unless `only_if_untested` is set.

## Reading the results

Each lane writes the Python, KiCad and wxPython it ran to the run's summary
and uploads its JUnit XML as an artifact named `junit-<OS>-<KiCad>`. GitHub
emails a failed scheduled run to whoever last edited the schedule line.

GitHub turns off a public repository's schedule after 60 days without
activity, and emails first. Re-enable it from the workflow's page in the
Actions tab.

## License

MIT; see [LICENSE](LICENSE).
