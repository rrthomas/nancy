import stream from 'stream'
import fs from 'fs'
import path from 'path'
import {ArgumentParser, RawDescriptionHelpFormatter} from 'argparse'
import packageJson from '../package.json'
import slimdom from 'slimdom'
// import formatXML from 'xml-formatter'
import fontoxpath from 'fontoxpath'
import which from 'which'
import execa from 'execa'
import PCRE2 from 'pcre2'
import stripFinalNewline from 'strip-final-newline'

const PCRE = PCRE2.PCRE2

function isExecutable(file: string) {
  try {
    fs.accessSync(file, fs.constants.X_OK)
    return true
  } catch {
    return false
  }
}

function dirTreeToXML(root: string) {
  const xtree = new slimdom.Document()
  const objToNode = (obj: string) => {
    const stats = fs.statSync(obj)
    const elem = xtree.createElement(stats.isDirectory() ? 'directory' : 'file')
    elem.setAttribute('name', path.basename(obj))
    elem.setAttribute('path', obj)
    if (isExecutable(obj)) {
      elem.setAttribute('executable', 'true')
    }
    if (stats.isDirectory()) {
      const dir = fs.readdirSync(obj, {withFileTypes: true})
      const dirs = dir.filter(dirent => dirent.isDirectory())
      const files = dir.filter(dirent => !(dirent.isDirectory()))
      dirs.forEach((dirent) => elem.appendChild(objToNode(path.join(obj, dirent.name))))
      files.forEach((dirent) => elem.appendChild(objToNode(path.join(obj, dirent.name))))
    }
    return elem
  }
  xtree.appendChild(objToNode(root))
  return xtree
}

function basenameToXPath(basename: string, nodeElement: string) {
  if (new Set(['.', '..']).has(basename)) {
    return basename
  }
  return `${nodeElement}[@name="${basename}"]`
}

function filePathToXPath(file: string, leafElement = '*', nodeElement = '*') {
  const fileArray = file === '' ? [] : file.split(path.sep)
  const steps = []
  for (const component of fileArray.slice(0, -1)) {
    steps.push(basenameToXPath(component, nodeElement))
  }
  if (fileArray.length > 0) {
    steps.push(basenameToXPath(fileArray[fileArray.length - 1], leafElement))
  }
  return steps
}

class Expander {
  xtree: slimdom.Document

  constructor(
    private template: string,
    private path: string,
    private root: string,
    private verbose: boolean,
  ) {
    this.xtree = dirTreeToXML(this.root)
    // console.error(formatXML(slimdom.serializeToWellFormedString(this.xtree)))
  }

  // Search for file starting at the given path; if found return its
  // Element; if not, die.
  private findOnPath(startPath: string, file: string) {
    const searchXPath = filePathToXPath(startPath)
    const fileXPath = filePathToXPath(file, 'file', 'directory')
    const thisSearchXPath = [`*`].concat(searchXPath, ['ancestor-or-self::*'], fileXPath).join('/')
    const match = fontoxpath.evaluateXPathToFirstNode(thisSearchXPath, this.xtree) as slimdom.Element
    if (match !== null) {
      const matchPath = match.getAttribute('path') as string
      if (this.verbose) {
        console.error(`  ${matchPath} ${(match.getAttribute('executable') ? '*' : '')}`)
      }
      return match
    }
    return null
  }

  private getFile(currentFile: string, leaf: string, args: string[]) {
    let output
    let newFile
    if (leaf === '-') {
      output = fs.readFileSync(process.stdin.fd)
      newFile = '-'
    } else {
      let startPath = this.path
      if (currentFile !== '-' && leaf === path.basename(currentFile)) {
        startPath = path.dirname(path.dirname(currentFile.replace(new RegExp(`^${this.root}${path.sep}`), '')))
      }
      const elem = this.findOnPath(startPath, leaf)
      if (elem !== null && !elem.getAttribute('executable')) {
        newFile = elem.getAttribute('path') as string
        output = fs.readFileSync(newFile)
      } else {
        newFile = elem !== null ? elem.getAttribute('path') as string : which.sync(leaf, {nothrow: true})
        if (newFile === null) {
          throw new Error(`cannot find \`${leaf}' while building \`${this.path}'`)
        }
        output = execa.sync(newFile, args).stdout
      }
    }
    return [newFile, output.toString('utf-8')]
  }

  expand(file: string, text: string) {
    // Set up macros
    type Macro = (...args: string[]) => string
    type Macros = {[key: string]: Macro}

    const macros: Macros = {
      path: () => this.path,
      root: () => this.root,
      template: () => this.template,
      include: (...args) => {
        const [newFile, output] = this.getFile(file, args[0], args.slice(1))
        return stripFinalNewline(this.expand(newFile, output))
      },
      paste: (...args) => {
        const [, output] = this.getFile(file, args[0], args.slice(1))
        return stripFinalNewline(output)
      },
    }

    const doMacro = (macro: string, arg?: string) => {
      const args = (arg || '').split(/(?<!\\),/)
      const expandedArgs: string[] = []
      for (const arg of args) {
        const unescapedArg = arg.replace(/\\,/g, ',') // Remove escaping backslashes
        expandedArgs.push(this.expand(file, unescapedArg))
      }
      if (macros[macro]) {
        return macros[macro](...expandedArgs)
      }
      // If macro is not found, reconstitute the call
      let res = `$${macro}`
      if (arg !== null) {
        res += `{${arg}}`
      }
      return res
    }

    // FIXME: Allow syntax to be redefined; e.g. use XML syntax: <[namespace:]include file="" />
    const re = new PCRE(String.raw`(\\)?\$(\p{L}(?:\p{L}|\p{N}|_)+)(\{((?:[^{}]++|(?3))*)})?`, 'guE')
    return re.replace(
      text,
      (_match: string, escaped: string, name: string, _args: string, args?: string) =>
        escaped === null ? doMacro(name, args) : `$${name}${_args}`
    )
  }
}

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
