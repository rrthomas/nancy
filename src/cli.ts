import path from 'path'
import fs from 'fs'
import {ArgumentParser, RawDescriptionHelpFormatter} from 'argparse'
import programVersion from './version.js'
// eslint-disable-next-line import/no-named-as-default
import expand from './index.js'

// Read and process arguments
const parser = new ArgumentParser({
  description: 'A simple templating system.',
  formatter_class: RawDescriptionHelpFormatter,
  epilog: `The INPUT-PATH is a '${path.delimiter}'-separated list; the inputs are merged\n`
    + 'in left-to-right order.\n\n'
    + 'OUTPUT cannot be in any input directory.',
})
parser.add_argument('input', {metavar: 'INPUT-PATH', help: 'list of input directories, or a single file'})
parser.add_argument('output', {metavar: 'OUTPUT', help: "output directory, or file ('-' for stdout)"})
parser.add_argument('--path', {help: "path to build relative to input tree [default: '']"})
parser.add_argument('--version', {
  action: 'version',
  version: `%(prog)s ${programVersion}
© 2002–2023 Reuben Thomas <rrt@sc3d.org>
https://github.com/rrthomas/nancy
Distributed under the GNU General Public License version 3, or (at
your option) any later version. There is no warranty.`,
})
interface Args {
  input: string
  output: string
  path?: string
  expander: string
}
const args: Args = parser.parse_args() as Args

// Expand input
try {
  if (args.input === '') {
    throw new Error('input path must not be empty')
  }
  const inputs = args.input.split(path.delimiter)

  // Deal with special case where INPUT is a single file and --path is not
  // given.
  let singleFileNoPath = false
  if (args.path === undefined && inputs.length === 1) {
    const stat = fs.statSync(inputs[0], {throwIfNoEntry: false})
    if (stat && stat.isFile()) {
      singleFileNoPath = true
      args.path = inputs[0]
      inputs[0] = process.cwd()
    }
  }

  // Check output is not under an input path provided we're not dealing with
  // the special case above.
  if (!singleFileNoPath) {
    for (const root of inputs) {
      const relative = path.relative(root, args.output)
      if (args.output !== '-' && relative !== '' && !relative.startsWith('..') && !path.isAbsolute(relative)) {
        throw new Error('output cannot be in any input directory')
      }
    }
  }
  expand(inputs, args.output, args.path)
} catch (error) {
  if (process.env.DEBUG) {
    console.error(error)
  } else {
    console.error(`${path.basename(process.argv[1])}: ${error}`)
  }
  process.exitCode = 1
}
