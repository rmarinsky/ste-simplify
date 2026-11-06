"""ste: one command for Simplified Technical English (STE).

  ste check PATH...              report problems (for CI: exit code 1 when there are errors)
  ste plan PATH...               numbered plan: safe replacements and sentences to write again
  ste apply [--skip N,N] PATH... apply the safe replacements that the person kept
  ste build-dictionary PDF       make your local dictionary from your copy of the standard

Run "ste COMMAND --help" for the options of a command.
"""
import sys

from . import __version__, build, check, fix


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0 if argv else 2
    if argv[0] == "--version":
        print(f"ste {__version__}")
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "check":
        return check.main(rest, prog="ste check")
    if cmd == "plan":
        return fix.main(rest, apply=False, prog="ste plan")
    if cmd == "apply":
        return fix.main(rest, apply=True, prog="ste apply")
    if cmd in ("build-dictionary", "build"):
        return build.main(rest)
    print(f"Unknown command: {cmd}\n\n{__doc__.strip()}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
