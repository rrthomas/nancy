#!/usr/bin/env -S node --no-warnings
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
import(path.join(__dirname, '..', 'lib', 'cli.js'))
