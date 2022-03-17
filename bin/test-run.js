#!/usr/bin/env ts-node-esm
import path from 'path'
import { fileURLToPath } from 'url'
const __dirname = path.dirname(fileURLToPath(import.meta.url))

import tsNode from 'ts-node'
import fs from 'fs-extra'
tsNode.register(fs.readJsonSync(path.join(__dirname, '../tsconfig.json')))

import '../src/cli.js'
