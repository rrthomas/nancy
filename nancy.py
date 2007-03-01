#! /usr/bin/env python
#
# (c) 2002-2006 Reuben Thomas (rrt@sc3d.org; http://rrt.sc3d.org/)
# Translated to Python by Tom Lynn
# Distributed under the GNU General Public License.

'''nancy.py -- The lazy web site maker'''

__author__ = "Reuben Thomas (rrt@sc3d.org; http://rrt.sc3d.org/)"
__version__ = "$Revision: 1 $"
__date__ = "$Date: $"
__description__ = "The lazy web site maker"

import sys
import os
import re
import optparse

USAGE = ("%prog DIRECTORY ROOT-FRAGMENT SEARCH-PATH\n" +
         "  DIRECTORY is the directory under which the fragments are kept\n" +
         "  ROOT-FRAGMENT is the root fragment to use\n" +
         "  SEARCH-PATH is the search path to use")

def include(fragment):
    '''Find an included file'''
    dir = searchpath
    while 1:
        name = os.path.join(dir, fragment)
        if fragment in os.listdir(dir) and os.path.isfile(name):
            if options.list_fragments: print >>sys.stderr, name
            return open(name).read()
        else:
            if dir=='.' or dir=='':
                sys.exit("Can't find fragment `%s'" % fragment)
            else:
                dir = os.path.dirname(dir)  # try parent dir

def expand(text):
    '''Expand includes in some text'''
    return re.sub(r"\$include{(.*?)}",
                  lambda match: expand(include(match.group(1))),
                  text)

# Command-line options
parser = optparse.OptionParser(USAGE, version='%prog 1.0')
parser.add_option('-l', '--list-fragments', action='store_true', default=False,
                  help='list fragments included (on stderr)')
# Get arguments
options, args = parser.parse_args()
if len(args) != 3:
    parser.print_help()
    parser.exit(2)

directory = args[0]
if not os.path.isdir(directory):
    parser.error("Directory `%s' not found or not a directory" % directory)

fragment = args[1]
searchPath = os.path.join(directory, args[2])

# Process file
sys.stdout.write(expand(include(fragment)))
