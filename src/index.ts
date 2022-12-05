import fs from 'fs-extra'
import path from 'path'
import which from 'which'
import {execaSync} from 'execa'
import stripFinalNewline from 'strip-final-newline'
import Debug from 'debug'

const debug = Debug('nancy')

const templateRegex = /\.nancy(?=\.[^.]+$|$)/
const noCopyRegex = /\.in(?=\.[^.]+$|$)/

function isExecutable(file: string): boolean {
  try {
    fs.accessSync(file, fs.constants.X_OK)
    return true
  } catch {
    return false
  }
}

function statSync(file: string): fs.Stats | undefined {
  return fs.statSync(file, {throwIfNoEntry: false})
}

export function expand(inputs: string[], outputPath: string, buildPath = ''): void {
  if (inputs.length === 0) {
    throw new Error('at least one input must be given')
  }

  type FullDirent = fs.Dirent & {path: string}
  type File = string
  type Directory = FullDirent[]
  type Dirent = File | Directory | undefined
  function isFile(object: Dirent): object is File {
    return typeof object === 'string'
  }
  function isDirectory(object: Dirent): object is Directory {
    return Array.isArray(object)
  }

  // Find the first file or directory with path `object` in the input tree,
  // scanning the roots from left to right.
  // If the result is a file, return its file system path.
  // If the result is a directory, return its contents as a list of
  // FullDirents, obtained by similarly scanning the tree from left to
  // right.
  // If something neither a file nor directory is found, raise an error.
  // If no result is found, return `undefined`.
  function findObject(object: string): Dirent {
    const dirs = []
    for (const root of inputs) {
      const stats = statSync(root)
      if (stats !== undefined && (stats.isDirectory() || object === '')) {
        const objectPath = path.join(root, object)
        const stats = statSync(objectPath)
        if (stats !== undefined) {
          if (stats.isFile()) {
            return objectPath
          }
          if (stats.isDirectory()) {
            dirs.push(objectPath)
          } else {
            throw new Error(`${objectPath} is not a file or directory`)
          }
        }
      }
    }
    const dirents: {[key: string]: FullDirent} = {}
    for (const dir of dirs.reverse()) {
      for (const dirent of fs.readdirSync(dir, {withFileTypes: true})) {
        const fullDirent: FullDirent = dirent as FullDirent
        fullDirent.path = path.join(dir, dirent.name)
        dirents[path.join(object, dirent.name)] = fullDirent
      }
    }
    return dirs.length > 0 ? Object.values(dirents) : undefined
  }

  const expandFile = (baseFile: string, filePath: string): string => {
    const innerExpand = (text: string, expandStack: string[]): string => {
      const doExpand = (text: string) => {
        // Search for file starting at the given path; if found return its file
        // name and contents; if not, die.
        const findOnPath = (startPath: string[], file: string) => {
          const search = [...startPath]
          const fileArray = path.normalize(file).split(path.sep)
          for (; ;) {
            const thisSearch = search.concat(fileArray)
            const objectPath = findObject(path.join(...thisSearch))
            if (isFile(objectPath) && !expandStack.includes(objectPath)) {
              return objectPath
            }
            if (search.pop() === undefined) {
              return undefined
            }
          }
        }

        const getFile = (leaf: string) => {
          debug(`Searching for ${leaf}`)
          const startPath = path.dirname(baseFile)
          const fileOrExec = findOnPath(startPath.split(path.sep), leaf)
            ?? which.sync(leaf, {nothrow: true})
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
            output = execaSync(file, args).stdout
          } else {
            output = fs.readFileSync(file)
          }
          return output.toString('utf-8')
        }

        // Set up macros
        type Macro = (...args: string[]) => string
        type Macros = {[key: string]: Macro}

        const macros: Macros = {
          path: () => baseFile,
          realpath: () => filePath,
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

    return innerExpand(fs.readFileSync(filePath, 'utf-8'), [filePath])
  }

  const getOutputPath = (baseFile: string) => (
    path.join(outputPath, baseFile.slice(buildPath.length)).replace(templateRegex, '')
  )

  const processFile = (baseFile: File, filePath: string): void => {
    const outputFile = getOutputPath(baseFile)
    debug(`Processing file ${filePath}`)
    if (templateRegex.exec(filePath)) {
      debug(`Expanding ${baseFile} to ${outputFile}`)
      fs.writeFileSync(outputFile, expandFile(baseFile, filePath))
    } else if (!noCopyRegex.exec(filePath)) {
      fs.copyFileSync(filePath, outputFile)
    }
  }

  const processPath = (object: string): void => {
    const dirent = findObject(object)
    if (dirent === undefined) {
      throw new Error(`'${object}' matches no path in the inputs`)
    }
    if (isDirectory(dirent)) {
      const outputDir = getOutputPath(object)
      debug(`Entering directory ${object}`)
      fs.ensureDirSync(outputDir)
      for (const childDirent of dirent) {
        if (childDirent.name[0] !== '.') {
          const childObject = path.join(object, childDirent.name)
          if (childDirent.isFile()) {
            processFile(childObject, childDirent.path)
          } else {
            processPath(childObject)
          }
        }
      }
    } else {
      processFile(object, dirent)
    }
  }

  processPath(buildPath)
}

export default expand
