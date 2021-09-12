import fs from 'fs-extra'
import {link} from 'linkfs'
import {IUnionFs, Union} from 'unionfs'
import path from 'path'
import which from 'which'
import execa from 'execa'
import stripFinalNewline from 'strip-final-newline'
import Debug from 'debug'

const debug = Debug('nancy')

const templateRegex = /\.nancy(?=\.[^.]+$|$)/
const noCopyRegex = /\.in(?=\.[^.]+$|$)/

function replacePathPrefix(s: string, prefix: string, newPrefix = ''): string {
  if (s.startsWith(prefix + path.sep)) {
    return path.join(newPrefix, s.slice(prefix.length + path.sep.length))
  }
  if (s === prefix) {
    return newPrefix
  }
  return s
}

// A supertype of `typeof(realFs)` and `IUnionFs`.
export type FS = Omit<IUnionFs, 'use'>

export function expand(inputs: string[], outputPath: string, buildPath = ''): void {
  const inputPath = inputs[0]

  const buildRoot = path.join(inputPath, buildPath)

  // Merge directories (and files) left-to-right
  const inputFs = new Union();
  for (const obj of inputs.reverse()) {
    inputFs.use(link(fs, [inputPath, obj]))
  }

  const isExecutable = (file: string): boolean => {
    try {
      inputFs.accessSync(file, fs.constants.X_OK)
      return true
    } catch {
      return false
    }
  }

  const expandFile = (baseFile: string): string => {
    const innerExpand = (text: string, expandStack: string[]): string => {
      const doExpand = (text: string) => {
        // Search for file starting at the given path; if found return its file
        // name and contents; if not, die.
        const findOnPath = (startPath: string[], file: string) => {
          const search = [...startPath]
          const fileArray = path.normalize(file).split(path.sep)
          for (; ;) {
            const thisSearch = search.concat(fileArray)
            const obj = path.join(inputPath, ...thisSearch)
            if (!expandStack.includes(obj) && inputFs.existsSync(obj)) {
              return obj
            }
            if (search.pop() === undefined) {
              return undefined
            }
          }
        }

        const getFile = (leaf: string) => {
          debug(`Searching for ${leaf}`)
          const startPath = replacePathPrefix(path.dirname(baseFile), inputPath)
          const pathStack = startPath.split(path.sep)
          const fileOrExec = findOnPath(pathStack, leaf) ?? which.sync(leaf, {nothrow: true})
          if (fileOrExec === null) {
            throw new Error(`cannot find '${leaf}' while expanding '${baseFile}'`)
          }
          debug(`Found ${fileOrExec}`)
          return fileOrExec
        }

        const readFile = (file: string, args: string[]) => {
          let output
          if (isExecutable(file)) {
            debug(`Running ${file} ${args.join(' ')}`)
            output = execa.sync(file, args).stdout
          } else {
            output = inputFs.readFileSync(file)
          }
          return output.toString('utf-8')
        }

        // Set up macros
        type Macro = (...args: string[]) => string
        type Macros = {[key: string]: Macro}

        const macros: Macros = {
          path: () => replacePathPrefix(path.dirname(baseFile), inputPath),
          root: () => inputPath,
          include: (...args) => {
            debug(`$include{${args.join(',')}}`)
            if (args.length < 1) {
              throw new Error('$include expects at least one argument')
            }
            const file = getFile(args[0])
            const output = readFile(file, args.slice(1))
            return stripFinalNewline(innerExpand(output, expandStack.concat(file)))
          },
          paste: (...args) => {
            debug(`paste{${args.join(',')}}`)
            if (args.length < 1) {
              throw new Error('$paste expects at least one argument')
            }
            const file = getFile(args[0])
            const output = readFile(file, args.slice(1))
            return stripFinalNewline(output)
          },
        }

        const doMacro = (macro: string, arg?: string) => {
          const args = (arg !== undefined) ? arg.split(/(?<!\\),/) : []
          const expandedArgs: string[] = []
          for (const arg of args) {
            const unescapedArg = arg.replace(/\\,/g, ',') // Remove escaping backslashes
            expandedArgs.push(doExpand(unescapedArg))
          }
          if (macros[macro] === undefined) {
            throw new Error(`no such macro '$${macro}'`)
          }
          return macros[macro](...expandedArgs)
        }

        const re = /(\\?)\$(\p{Letter}(?:\p{Letter}|\p{Number}|_)*)/gu
        let res
        let expanded = text
        while ((res = re.exec(expanded)) !== null) {
          const escaped = res[1]
          const name = res[2]
          let args
          if (expanded[re.lastIndex] === '{') {
            const argsStart = re.lastIndex
            let depth = 1
            let nextIndex
            for (nextIndex = argsStart + 1; nextIndex < expanded.length; nextIndex += 1) {
              if (expanded[nextIndex] === '}') {
                depth -= 1
                if (depth === 0) {
                  break
                }
              } else if (expanded[nextIndex] === '{') {
                depth += 1
              }
            }
            if (nextIndex === expanded.length) {
              throw new Error('missing close brace')
            }
            // Update re to restart matching past close brace
            re.lastIndex = nextIndex + 1
            args = doExpand(expanded.slice(argsStart + 1, nextIndex))
          }
          let output
          if (escaped !== '') {
            // Just remove the leading '\'
            output = `$${name}${args !== undefined ? `{${args}}` : ''}`
          } else {
            output = doMacro(name, args)
          }
          expanded = expanded.slice(0, res.index) + output + expanded.slice(re.lastIndex)
          // Update re to restart matching after output of macro
          re.lastIndex = res.index + output.length
        }

        return expanded
      }

      return doExpand(text)
    }

    return innerExpand(inputFs.readFileSync(baseFile, 'utf-8'), [baseFile])
  }

  const expandPath = (obj: string): void => {
    const outputObj = replacePathPrefix(obj, buildRoot, outputPath).replace(templateRegex, '')
    const stats = inputFs.statSync(obj)
    if (stats.isDirectory()) {
      fs.ensureDirSync(outputObj)
      for (const dirent of inputFs.readdirSync(obj)) {
        if (dirent[0] !== '.') {
          expandPath(path.join(obj, dirent))
        }
      }
    } else if (stats.isFile()) {
      if (templateRegex.exec(obj)) {
        debug(`Expanding ${obj} to ${outputObj}`)
        fs.writeFileSync(outputObj, expandFile(obj))
      } else if (!noCopyRegex.exec(obj)) {
        fs.copyFileSync(obj, outputObj)
      }
    } else {
      throw new Error(`'${obj}' is not a directory or file`)
    }
  }

  expandPath(buildRoot)
}

export default expand
