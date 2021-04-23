import stream from 'stream'
import fs from 'fs'
import path from 'path'
import {Command, flags} from '@oclif/command'
import which from 'which'
import execa from 'execa'
import PCRE2 = require('pcre2')
import stripFinalNewline = require('strip-final-newline')

const PCRE = PCRE2.PCRE2

function isExecutable(file: string) {
  try {
    fs.accessSync(file, fs.constants.X_OK)
    return true
  } catch {
    return false
  }
}

class Expander {
  constructor(
    private template: string,
    private path: string,
    private root: string,
    private verbose: boolean,
  ) {}

  expand(file: string, text: string) {
    // Search for file starting at the given path; if found return its file
    // name and contents; if not, die.
    const findOnPath = (startPath: string, file: string) => {
      const fileArray = file.split(path.sep)
      const search = startPath.split(path.sep)
      while (fileArray[0] === '..') {
        fileArray.shift()
        search.pop()
      }
      for (;;) {
        const thisSearch = search.concat(fileArray)
        const obj = path.join(this.root, ...thisSearch)
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

    const getFile = (leaf: string) => {
      let startPath = this.path
      if (file !== '-' && leaf === path.basename(file)) {
        startPath = path.dirname(path.dirname(file.replace(new RegExp(`^${this.root}/`), '')))
      }
      let newfile
      if (leaf === '-') {
        newfile = leaf
      } else {
        const fileOrExec = findOnPath(startPath, leaf) || which.sync(leaf, {nothrow: true})
        if (fileOrExec === null) {
          throw new Error(`cannot find \`${leaf}' while building \`${path}'`)
        }
        newfile = fileOrExec
      }
      return newfile
    }

    const readFile = (file: string, args: string[]) => {
      let output
      if (file === '-') {
        output = fs.readFileSync(process.stdin.fd)
      } else if (isExecutable(file)) {
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
      return output.toString('utf-8')
    }

    // Set up macros
    type Macro = (...args: string[]) => string
    type Macros = { [key: string]: Macro }

    const macros: Macros = {
      path: () => this.path,
      root: () => this.root,
      template: () => this.template,
      include: (...args) => {
        const file = getFile(args[0])
        const output = readFile(file, args.slice(1))
        return stripFinalNewline(this.expand(file, output))
      },
      paste: (...args) => {
        const file = getFile(args[0])
        const output = readFile(file, args.slice(1))
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
    const re = new PCRE(String.raw`(?:\\)?\$(\p{L}(?:\p{L}|\p{N}|_)+)(\{((?:[^{}]++|(?2))*)})?`, 'guE')
    return re.replace(
      text,
      (_match: string, name: string, _args: string, args?: string) => doMacro(name, args)
    )
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

    fh.write(
      new Expander(args.template, args.path, flags.root, flags.verbose)
        .expand('-', '$include{$template}')
    )
  }
}

export = Nancy
