import stream from 'stream'
import fs from 'fs'
import path from 'path'
import {Command, flags} from '@oclif/command'
import which from 'which'
import execa from 'execa'
import PCRE2 = require('pcre2')
import stripFinalNewline = require('strip-final-newline')

const PCRE = PCRE2.PCRE2

type Macro = (...args: string[]) => string
type Macros = { [key: string]: Macro }

function isExecutable(file: string) {
  try {
    fs.accessSync(file, fs.constants.X_OK)
    return true
  } catch {
    return false
  }
}

class Expander {
  template: string

  path: string

  root: string

  file: string[] = [] // Stack of file names being considered in getFile

  verbose: boolean

  constructor(template: string, path: string, root: string, verbose: boolean) {
    this.template = template
    this.path = path
    this.root = root
    this.verbose = verbose
  }

  // Set up macros
  macros: Macros = {
    path: () => this.path,
    root: () => this.root,
    template: () => this.template,
    include: (...args) => this.getFile(text => this.expand(text), args[0], args.slice(1)),
    paste: (...args) => this.getFile(text => text, args[0], args.slice(1)),
  }

  doMacro(macro: string, arg?: string) {
    const args = (arg || '').split(/(?<!\\),/)
    const expandedArgs: string[] = []
    for (const arg of args) {
      const unescapedArg = arg.replace(/\\,/g, ',') // Remove escaping backslashes
      expandedArgs.push(this.expand(unescapedArg))
    }
    if (this.macros[macro]) {
      return this.macros[macro](...expandedArgs)
    }
    // If macro is not found, reconstitute the call
    let res = `$${macro}`
    if (arg !== null) {
      res += `{${arg}}`
    }
    return res
  }

  // FIXME: Allow syntax to be redefined; e.g. use XML syntax: <[namespace:]include file="" />
  expand(text: string) {
    const re = new PCRE(String.raw`(?:\\)?\$(\p{L}(?:\p{L}|\p{N}|_)+)(\{((?:[^{}]++|(?2))*)})?`, 'guE')
    return re.replace(
      text,
      (_match: string, name: string, _args: string, args?: string) => this.doMacro(name, args)
    )
  }

  // Search for file starting at the given path; if found return its file
  // name and contents; if not, die.
  findOnPath(startPath: string, file: string, root: string) {
    const fileArray = file.split(path.sep)
    const search = startPath.split(path.sep)
    while (fileArray[0] === '..') {
      fileArray.shift()
      search.pop()
    }
    for (;;) {
      const thisSearch = search.concat(fileArray)
      const obj = path.join(root, ...thisSearch)
      if (fs.existsSync(obj)) {
        if (this.verbose) {
          console.error(`  ${obj} ${(isExecutable(obj) ? '*' : '')}`)
        }
        return obj
      }
      if (search.length === 0) {
        break
      }
      search.pop()
    }
    return null
  }

  // FIXME: de-uglify implementation of startPath
  getFile(processor: Macro, leaf: string, args: string[]) {
    let startPath = this.path
    if (this.file.length > 0 && leaf === path.basename(this.file[0])) {
      startPath = path.dirname(path.dirname(
        this.file[0].replace(new RegExp(`^${this.root}/`), '')
      ))
    }
    let output
    let file
    if (leaf === '-') {
      output = fs.readFileSync(process.stdin.fd)
      file = leaf
    } else {
      const fileOrExec = this.findOnPath(startPath, leaf, this.root) || which.sync(leaf, {nothrow: true})
      if (fileOrExec === null) {
        throw new Error(`cannot find \`${leaf}' while building \`${this.path}'`)
      }
      file = fileOrExec
      if (isExecutable(file)) {
        try {
          output = execa.sync(file, args).stdout
        } catch {
          throw new Error(`could not run \`${file}'`)
        }
      } else {
        try {
          output = fs.readFileSync(file)
        } catch {
          throw new Error(`error reading \`${file}'`)
        }
      }
    }
    output = output.toString('utf-8')

    this.file.unshift(file)
    const res = stripFinalNewline(processor(output))
    this.file.shift()
    return res
  }
}

class Nancy extends Command {
  static description = 'A simple templating system.'

  static flags = {
    version: flags.version(),
    help: flags.help({char: 'h'}),
    output: flags.string({description: '[default: standard output] output file'}),
    root: flags.string({description: 'source root', default: process.cwd()}),
    verbose: flags.boolean({description: 'show on standard error the path being built, and the names of files built, included and pasted'}),
  }

  static args = [
    {name: 'template', description: 'template file name', required: true},
    {name: 'path', description: 'desired path to build', required: true},
  ]

  async run() {
    const {args, flags} = this.parse(Nancy)

    if (flags.verbose) {
      console.error(`${args.path}:`)
    }

    // Build path
    let fh: stream.Writable = process.stdout
    if (flags.output !== undefined && flags.output !== '-') {
      fh = fs.createWriteStream(flags.output)
    }

    const expander = new Expander(args.template, args.path, flags.root, flags.verbose)
    const expanded = expander.expand('$include{$template}')
    fh.write(expanded)
  }
}

export = Nancy
