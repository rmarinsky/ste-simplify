"""ste: one command for Simplified Technical English (STE).

  ste prepare [PDF]                       make your local dictionary (downloads the PDF from ASD if necessary)
  ste scan PATH...                        report problems (exit code 1 when there are errors)
  ste fix PATH...                         numbered plan: safe replacements and sentences to write again
  ste fix --apply [--skip N,N] PATH...    write the safe replacements that the person kept

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
    if cmd == "prepare":
        return build.main(rest)
    if cmd == "scan":
        return check.main(rest)
    if cmd == "fix":
        return fix.main(rest)
    print(f"Unknown command: {cmd}\n\n{__doc__.strip()}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
