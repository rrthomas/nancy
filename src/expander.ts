import fs from 'fs-extra'
import realFs from 'fs'
import {IFS} from 'unionfs/lib/fs'
import path from 'path'
import Debug from 'debug'

const debug = Debug('nancy')

export function replacePathPrefix(s: string, prefix: string, newPrefix = ''): string {
  if (s.startsWith(prefix + path.sep)) {
    return path.join(newPrefix, s.slice(prefix.length + path.sep.length))
  } else if (s === prefix) {
    return newPrefix
  }
  return s
}

export abstract class Expander {

  // FIXME: arguments except input should be arguments to expand()
  constructor(
    protected input: string,
    protected output: string,
    protected path = '',
    protected abortOnError = false,
    protected inputFs: IFS = realFs,
  ) {}

  protected static templateRegex = /\.nancy\.(?=\.[^.]+$)?/
  protected static noCopyRegex = /\.in(?=\.[^.]+$)?/

  protected abstract expandFile(filePath: string): string

  isExecutable(file: string): boolean {
    try {
      this.inputFs.accessSync(file, fs.constants.X_OK)
      return true
    } catch {
      return false
    }
  }

  private expandPath(obj: string): void {
    const outputPath = replacePathPrefix(obj, path.join(this.input, this.path), this.output)
      .replace(Expander.templateRegex, '.')
    const stats = this.inputFs.statSync(obj)
    if (stats.isDirectory()) {
      fs.emptyDirSync(outputPath)
      const dir = this.inputFs.readdirSync(obj, {withFileTypes: true})
        .filter(dirent => dirent.name[0] !== '.')
      const dirs = dir.filter(dirent => dirent.isDirectory())
      const files = dir.filter(dirent => !dirent.isDirectory())
      dirs.forEach((dirent) => this.expandPath(path.join(obj, dirent.name)))
      files.forEach((dirent) => this.expandPath(path.join(obj, dirent.name)))
    } else {
      if (Expander.templateRegex.exec(obj)) {
        debug(`Expanding ${obj} to ${outputPath}`)
        fs.writeFileSync(outputPath, this.expandFile(obj))
      } else if (!Expander.noCopyRegex.exec(obj)) {
        fs.copyFileSync(obj, outputPath)
      }
    }
  }

  expand(): void {
    const obj = path.join(this.input, this.path)
    if (!this.inputFs.existsSync(obj)) {
      throw new Error(`path '${this.path}' does not exist in '${this.input}'`)
    }
    this.expandPath(obj)
  }
}

export default Expander
