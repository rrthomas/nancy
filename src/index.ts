import stream from 'stream'
import fs from 'fs'
import path from 'path'
import {ArgumentParser, RawDescriptionHelpFormatter} from 'argparse'
const packageJson = require('../package.json')
import dirTree = require('directory-tree')
import {DOMImplementation/* , XMLSerializer */} from 'xmldom'
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

interface File {
  name: string;
  path: string;
  executable: boolean;
}

interface FileTree extends File {
  children?: FileTree[];
}

function dirTreeContents(filepath: string) {
  return dirTree(
    filepath, {normalizePath: true},
    (item: FileTree, filepath: string) => {
      item.executable = isExecutable(filepath)
    },
  )
}

function dirTreeToXML(root: string, tree: any) {
  const xtree = new DOMImplementation().createDocument(null, 'tree', null)
  const objToNode = (obj: FileTree) => {
    const elem = xtree.createElement(obj.children ? 'directory' : 'file')
    elem.setAttribute('name', obj.name)
    elem.setAttribute('path', obj.path)
    if (obj.executable) {
      elem.setAttribute('executable', 'true')
    }
    if (obj.children) {
      const dirs = obj.children.filter(child => child.children)
      const files = obj.children.filter(child => !child.children)
      dirs.forEach((child: FileTree) => elem.appendChild(objToNode(child)))
      files.forEach((child: FileTree) => elem.appendChild(objToNode(child)))
    }
    return elem
  }
  // The following should work, but Element.append and spreading/iteration
  // of NodeList are not yet implemented in xmldom.
  // xtree.documentElement.append(...objToNode(tree).childNodes)
  const fragment = xtree.createDocumentFragment()
  // eslint-disable-next-line unicorn/prefer-spread
  Array.from(objToNode(tree).childNodes).forEach((node: Node) => fragment.appendChild(node))
  xtree.documentElement.appendChild(fragment)
  xtree.documentElement.setAttribute('name', '')
  xtree.documentElement.setAttribute('path', root)
  return xtree
}

function basenameToXPath(basename: string, nodeElement: string) {
  if (new Set(['.', '..']).has(basename)) {
    return basename
  }
  return `${nodeElement}[@name="${basename}"]`
}

function filePathToXPath(file: string, leafElement = 'directory', nodeElement = 'directory') {
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
  tree: any

  xtree: Document

  constructor(
    private template: string,
    private path: string,
    private root: string,
    private verbose: boolean,
  ) {
    this.tree = dirTreeContents(root)
    this.xtree = dirTreeToXML(this.root, this.tree)
    // console.error(formatXML(new XMLSerializer().serializeToString(this.xtree)))
  }

  // Search for file starting at the given path; if found return its file
  // name and contents; if not, die.
  private findOnPath(startPath: string, file: string) {
    const searchXPath = filePathToXPath(startPath, '*', '*')
    const fileXPath = filePathToXPath(file, 'file')
    const thisSearchXPath = ['tree'].concat(searchXPath, ['ancestor-or-self::*'], fileXPath).join('/')
    const match = fontoxpath.evaluateXPathToFirstNode(thisSearchXPath, this.xtree) as Element
    if (match !== null) {
      const matchPath = match.getAttribute('path') as string
      if (this.verbose) {
        console.error(`  ${matchPath} ${(match.getAttribute('executable') ? '*' : '')}`)
      }
      return matchPath
    }
    return null
  }

  private readFile(file: string, args: string[]) {
    let output
    if (file === '-') {
      output = fs.readFileSync(process.stdin.fd)
    } else if (isExecutable(file)) {
      output = execa.sync(file, args).stdout
    } else {
      output = fs.readFileSync(file)
    }
    return output.toString('utf-8')
  }

  private getFile(currentFile: string, leaf: string) {
    if (leaf === '-') {
      return leaf
    }
    let startPath = this.path
    if (currentFile !== '-' && leaf === path.basename(currentFile)) {
      startPath = path.dirname(path.dirname(currentFile.replace(new RegExp(`^${this.root}${path.sep}`), '')))
    }
    const fileOrExec = this.findOnPath(startPath, leaf) || which.sync(leaf, {nothrow: true})
    if (fileOrExec === null) {
      throw new Error(`cannot find \`${leaf}' while building \`${this.path}'`)
    }
    return fileOrExec
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
        const newFile = this.getFile(file, args[0])
        const output = this.readFile(newFile, args.slice(1))
        return stripFinalNewline(this.expand(newFile, output))
      },
      paste: (...args) => {
        const newFile = this.getFile(file, args[0])
        const output = this.readFile(newFile, args.slice(1))
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
const args = parser.parse_args()

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
