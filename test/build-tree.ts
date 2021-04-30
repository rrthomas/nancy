#!/usr/bin/env ts-node

import fs from 'fs'
import path from 'path'
import walk from 'walkdir'
import execa from 'execa'
import yargs from 'yargs/yargs'
import {hideBin} from 'yargs/helpers'

// Turn a directory into a map of subdirectories to 'leaf' | 'node'
function scanDir(root_: string) {
  const root = path.resolve(root_)
  const dirs: {[name: string]: ('leaf' | 'node')} = {}
  walk.sync(root, {no_return: true}, (objPath, stats) => {
    if (!stats.isDirectory()) {
      return
    }
    const dir = objPath.replace(new RegExp(`^${root}(?:${path.sep})?`), '')
    if (dirs[dir] === undefined) {
      dirs[dir] = 'leaf'
    }
    let parent = path.dirname(dir)
    if (parent === '.') {
      parent = ''
    }
    dirs[parent] = 'node'
  })
  return dirs
}

// Read and process arguments
try {
  yargs(hideBin(process.argv))
    .command(
      '$0 <srcRoot> <template> <destRoot>',
      'Build a directory tree with Nancy',
      () => { /* empty builder */ },
      (argv: {[name: string]: string})  => {
        // Process source directories; work in sorted order so we process
        // create directories in the destination tree before writing their
        // contents
        const sources = scanDir(argv.srcRoot)
        for (const dir of Object.keys(sources).sort()) {
          const dest = path.join(argv.destRoot, dir)
          if (sources[dir] === 'leaf') { // Process a leaf directory into a page
            const nancy_cmd = process.env.NANCY
            if (nancy_cmd === undefined) {
              throw new Error('Environment variable `NANCY\' not set')
            }
            try {
              execa.sync(
                nancy_cmd,
                [
                  '--verbose',
                  `--root=${argv.srcRoot}`,
                  `--output=${path.join(argv.destRoot, dir)}`,
                  argv.template,
                  dir,
                ]
              )
            } catch (error) {
              throw new Error(`Problem building \`${dir}': ${error}`)
            }
          } else if (dir !== '') { // Make a non-leaf directory
            try {
              fs.mkdirSync(dest)
            } catch (error) {
              throw new Error(`Error creating \`${dir}': ${error}`)
            }
          }
        }
      }).argv
} catch (error) {
  console.error(`${path.basename(process.argv[1])}: ${error}`)
  process.exitCode = 1
}
