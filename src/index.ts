import stream from 'stream'
import fs from 'fs'
import {ArgumentParser, RawDescriptionHelpFormatter} from 'argparse'
import packageJson from '../package.json'
import {Expander} from './expander'

// Read and process arguments
const parser = new ArgumentParser({
  description: 'A simple templating system.',
  epilog: 'Use `-\' as a file name to indicate standard input or output.',
  formatter_class: RawDescriptionHelpFormatter,
})
parser.add_argument('template', {metavar: 'TEMPLATE', help: 'template file name'})
parser.add_argument('path', {metavar: 'PATH', help: 'desired path to build'})
parser.add_argument('--output', {
  default: '-',
  help: 'output file [default: %(default)s]',
})
parser.add_argument('--root', {
  default: process.cwd(),
  help: 'source root [default: current directory]',
})
parser.add_argument('--verbose', {
  action: 'store_true',
  help: 'show on standard error the path being built, and the names of files built, included and pasted',
})
parser.add_argument('--version', {
  action: 'version',
  version: `%(prog)s ${packageJson.version}
(c) 2002-2021 Reuben Thomas <rrt@sc3d.org>
https://github.com/rrthomas/nancy/
Distributed under the GNU General Public License version 3, or (at
your option) any later version. There is no warranty.`,
})
interface Args {
  template: string;
  path: string;
  output: string;
  root: string;
  verbose: boolean;
}
const args: Args = parser.parse_args() as Args

if (args.verbose) {
  console.error(`${args.path}:`)
}

// Build path
let fh: stream.Writable = process.stdout
if (args.output !== undefined && args.output !== '-') {
  fh = fs.createWriteStream(args.output)
}

fh.write(
  new Expander(args.template, args.path, args.root, args.verbose)
    .expand('-', '$include{$template}')
)
