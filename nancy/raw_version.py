"""RawDescription-formatted --version output for argparse.

This file is in the public domain.

Code adapted from https://stackoverflow.com/a/75373746
"""

import argparse
import sys


class RawVersionAction(argparse._VersionAction):
    """Customized _VersionAction with RawDescription-formatted output."""

    def __call__(self, parser, namespace, values, option_string=None):
        version = self.version
        formatter = argparse.RawDescriptionHelpFormatter(prog=parser.prog)
        formatter.add_text(version)
        parser._print_message(formatter.format_help(), sys.stdout)
        parser.exit()
