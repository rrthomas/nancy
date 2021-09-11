import path from 'path'
import {ArgumentParser, RawDescriptionHelpFormatter} from 'argparse'
import programVersion from './version'
// eslint-disable-next-line import/no-named-as-default
import expand, {unionFs} from './index'

// Read and process arguments
const parser = new ArgumentParser({
  description: 'A simple templating system.',
  formatter_class: RawDescriptionHelpFormatter,
  epilog: `The INPUT-PATH is a '${path.delimiter}'-separated list; the inputs\n`
    + 'are merged in left-to-right order.',
})
parser.add_argument('input', {metavar: 'INPUT-PATH', help: 'list of input directories (or files)'})
parser.add_argument('output', {metavar: 'OUTPUT', help: 'output directory (or file)'})
parser.add_argument('--path', {help: 'path to build relative to input tree [default: /]'})
parser.add_argument('--version', {
  action: 'version',
  version: `%(prog)s ${programVersion}
(c) 2002-2021 Reuben Thomas <rrt@sc3d.org>
https://github.com/rrthomas/nancy/
Distributed under the GNU General Public License version 3, or (at
your option) any later version. There is no warranty.`,
})
interface Args {
  input: string;
  output: string;
  path?: string;
  verbose: boolean;
  expander: string;
}
const args: Args = parser.parse_args() as Args

// Expand input
try {
  if (args.input === '') {
    throw new Error('input path must not be empty')
  }
  const inputs = args.input.split(path.delimiter)
  expand(inputs[0], args.output, args.path, unionFs(inputs))
} catch (error) {
  if (process.env.DEBUG) {
    console.error(error)
  } else {
    console.error(`${path.basename(process.argv[1])}: ${error}`)
  }
  process.exitCode = 1
}
