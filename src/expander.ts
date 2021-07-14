import fs from 'fs-extra'
import realFs from 'fs'
import {IFS} from 'unionfs/lib/fs'
import path from 'path'
import which from 'which'
import execa from 'execa'
import stripFinalNewline from 'strip-final-newline'
import Debug from 'debug'

const debug = Debug('nancy')

const templateRegex = /\.nancy\.(?=\.[^.]+$)?/
const noCopyRegex = /\.in(?=\.[^.]+$)?/

function replacePathPrefix(s: string, prefix: string, newPrefix = ''): string {
  if (s.startsWith(prefix + path.sep)) {
    return path.join(newPrefix, s.slice(prefix.length + path.sep.length))
  } else if (s === prefix) {
    return newPrefix
  }
  return s
}

function expand(inputPath: string, outputPath: string, buildPath = '', abortOnError = false, inputFs: IFS = realFs): void {
  const isExecutable = (file: string): boolean => {
    try {
      inputFs.accessSync(file, fs.constants.X_OK)
      return true
    } catch {
      return false
    }
  }

  const expandPath = (obj: string): void => {
    const outputObj = replacePathPrefix(obj, path.join(inputPath, buildPath), outputPath)
      .replace(templateRegex, '.')
    const stats = inputFs.statSync(obj)
    if (stats.isDirectory()) {
      fs.emptyDirSync(outputObj)
      const dir = inputFs.readdirSync(obj, {withFileTypes: true})
        .filter(dirent => dirent.name[0] !== '.')
      const dirs = dir.filter(dirent => dirent.isDirectory())
      const files = dir.filter(dirent => !dirent.isDirectory())
      dirs.forEach((dirent) => expandPath(path.join(obj, dirent.name)))
      files.forEach((dirent) => expandPath(path.join(obj, dirent.name)))
    } else {
      if (templateRegex.exec(obj)) {
        debug(`Expanding ${obj} to ${outputObj}`)
        fs.writeFileSync(outputObj, expandFile(obj))
      } else if (!noCopyRegex.exec(obj)) {
        fs.copyFileSync(obj, outputObj)
      }
    }
  }

  const expandFile = (baseFile: string): string => {
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
            const obj = path.join(inputPath, ...thisSearch)
            if (inputFs.existsSync(obj)) {
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
          const startPath = replacePathPrefix(path.dirname(baseFile), inputPath)
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
          if (isExecutable(file)) {
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
          path: () => replacePathPrefix(path.dirname(baseFile), inputPath)
            .replace(templateRegex, '.'),
          root: () => inputPath,
          include: (...args) => {
            debug(`$include{${args.join(',')}}`)
            const file = getFile(args[0])
            const output = readFile(file, args.slice(1))
            return stripFinalNewline(innerExpand(output, expandStack.concat(file)))
          },
          // FIXME: When called with no arguments, it pastes the current file
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
            if (abortOnError) {
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

        const re = /(\\?)\$(\p{Letter}(?:\p{Letter}|\p{Number}|_)+)/gu
        let res
        while ((res = re.exec(text)) !== null) {
          const escaped = res[1]
          const name = res[2]
          let args
          if (text[re.lastIndex] === '{') {
            const argsStart = re.lastIndex
            let depth = 1
            let nextChar
            for (nextChar = argsStart + 1; nextChar < text.length; nextChar += 1) {
              if (text[nextChar] === '}') {
                depth -= 1
                if (depth === 0) {
                  break
                }
              } else if (text[nextChar] === '{') {
                depth += 1
              }
            }
            if (nextChar === text.length) {
              throw new Error('missing close brace')
            }
            // Update re to restart matching past close brace
            re.lastIndex = nextChar + 1
            args = doExpand(text.slice(argsStart + 1, nextChar))
          }
          let output
          if (escaped !== '') {
            output = `$${name}${args !== undefined ? `{${args}}` : ''}`
          } else {
            output = doMacro(name, args)
          }
          text = text.slice(0, res.index) + output + text.slice(re.lastIndex)
          // Update re to restart matching after output of macro
          re.lastIndex = res.index + output.length
        }

        return text
      }

      return doExpand(text)
    }

    return innerExpand(inputFs.readFileSync(baseFile, 'utf-8'), [baseFile])
  }

  expandPath(path.join(inputPath, buildPath))
}

export default expand
