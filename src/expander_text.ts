import path from 'path'
import which from 'which'
import execa from 'execa'
import {PCRE2} from 'pcre2'
import stripFinalNewline from 'strip-final-newline'
import {Expander, replacePathPrefix} from './expander'
import Debug from 'debug'

const debug = Debug('nancy-text')

export class TextExpander extends Expander {
  protected expandFile(baseFile: string): string {
    const innerExpand = (text: string, expandStack: string[]): string => {
      const doExpand = (text: string) => {
        // Search for file starting at the given path; if found return its file
        // name and contents; if not, die.
        const findOnPath = (startPath: string[], file: string) => {
          const search = [...startPath]
          const fileArray = file.split(path.sep)
          for (; fileArray[0] === '..'; fileArray.shift()) {
            search.pop()
          }
          for (; ; search.pop()) {
            const thisSearch = search.concat(fileArray)
            const obj = path.join(this.input, ...thisSearch)
            if (this.inputFs.existsSync(obj)) {
              return obj
            }
            if (search.length === 0) {
              break
            }
          }
          return undefined
        }

        const getFile = (leaf: string) => {
          debug(`Searching for ${leaf}`)
          const startPath = replacePathPrefix(path.dirname(baseFile), this.input)
          let fileOrExec
          for (const pathStack = startPath.split(path.sep); ; pathStack.pop()) {
            fileOrExec = findOnPath(pathStack, leaf)
            if (fileOrExec === undefined || !expandStack.includes(fileOrExec) || pathStack.length === 0) {
              break
            }
          }
          fileOrExec = fileOrExec ?? which.sync(leaf, {nothrow: true})
          if (fileOrExec === null) {
            throw new Error(`cannot find '${leaf}' while expanding '${baseFile}'`)
          }
          debug(`Found ${fileOrExec}`)
          return fileOrExec
        }

        const readFile = (file: string, args: string[]) => {
          let output
          if (this.isExecutable(file)) {
            output = execa.sync(file, args).stdout
          } else {
            output = this.inputFs.readFileSync(file)
          }
          return output.toString('utf-8')
        }

        // Set up macros
        type Macro = (...args: string[]) => string
        type Macros = {[key: string]: Macro}

        const macros: Macros = {
          path: () => replacePathPrefix(path.dirname(baseFile), this.input)
            .replace(Expander.templateRegex, '.'),
          root: () => this.input,
          include: (...args) => {
            debug(`$include{${args.join(',')}}`)
            const file = getFile(args[0])
            const output = readFile(file, args.slice(1))
            return stripFinalNewline(innerExpand(output, expandStack.concat(file)))
          },
          paste: (...args) => {
            debug(`paste{${args.join(',')}}`)
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
            expandedArgs.push(doExpand(unescapedArg))
          }
          try {
            return macros[macro](...expandedArgs)
          } catch (error) {
            if (this.abortOnError) {
              if (macros[macro] !== undefined) {
                throw error
              }
              throw new Error(`no such macro '${macro}'`)
            }
            // Reconstitute the call
            let res = `$${macro}`
            if (arg !== null) {
              res += `{${arg}}`
            }
            return res
          }
        }

        const re = new PCRE2(String.raw`(\\?)\$(\p{L}(?:\p{L}|\p{N}|_)+)(\{((?:[^{}]++|(?3))*)})?`, 'guE')
        return re.replace(
          text,
          (_match: string, escaped: string, name: string, _args?: string, args?: string) => {
            if (escaped === '\\') {
              return `$${name}${_args ? _args : ''}`
            }
            return doMacro(name, args)
          }
        )
      }

      return doExpand(text)
    }

    return innerExpand(this.inputFs.readFileSync(baseFile, 'utf-8'), [baseFile])
  }
}
