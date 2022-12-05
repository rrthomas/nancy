import util from 'util'
import fs from 'fs'
import path from 'path'
import net from 'net'
import {execa} from 'execa'
import {temporaryFile, temporaryDirectory} from 'tempy'
import {compareSync, Difference} from 'dir-compare'
import chai, {assert, expect} from 'chai'
import chaiAsPromised from 'chai-as-promised'
import {check} from 'linkinator'

import {expand} from '../src/index.js'

chai.use(chaiAsPromised)

const command = process.env.NODE_ENV === 'coverage' ? '../bin/test-run.js' : '../bin/run.js'

async function run(args: string[]) {
  return execa(command, args)
}

function diffsetDiffsOnly(diffSet: Difference[]): Difference[] {
  return diffSet.filter((diff) => diff.state !== 'equal')
}

function assertFileObjEqual(obj: string, expected: string) {
  const compareResult = compareSync(obj, expected, {compareContent: true})
  assert(
    compareResult.same,
    util.inspect(diffsetDiffsOnly(compareResult.diffSet as Difference[])),
  )
}

function test(inputDirs: string[], expected: string, buildPath?: string) {
  const outputDir = temporaryDirectory()
  const outputObj = path.join(outputDir, 'output')
  if (buildPath !== undefined) {
    expand(inputDirs, outputObj, buildPath)
  } else {
    expand(inputDirs, outputObj)
  }
  assertFileObjEqual(outputObj, expected)
  fs.rmSync(outputDir, {recursive: true})
}

function failingTest(inputDirs: string[], expected: string) {
  const outputDir = temporaryDirectory()
  try {
    test(inputDirs, outputDir)
  } catch (error: any) {
    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
    expect(error.message).to.contain(expected)
    return
  } finally {
    fs.rmSync(outputDir, {recursive: true})
  }
  throw new Error('test passed unexpectedly')
}

async function failingCliTest(args: string[], expected: string) {
  const outputDir = temporaryDirectory()
  try {
    await run(args.concat(outputDir))
  } catch (error: any) {
    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
    expect(error.stderr).to.contain(expected)
    return
  } finally {
    fs.rmSync(outputDir, {recursive: true})
  }
  throw new Error('test passed unexpectedly')
}

async function checkLinks(root: string, start: string) {
  const results = await check({path: start, serverRoot: root})
  if (!results.passed) {
    console.error(results)
  }
  assert(results.passed, 'Broken links in output')
}

describe('nancy', function t() {
  // In coverage mode, allow for recompilation.
  this.timeout(10000)

  before(() => {
    process.chdir('test')
  })

  // Module tests
  it('Whole-tree test', async () => {
    test(['webpage-src'], 'webpage-expected')
    await checkLinks('webpage-expected', 'index.html')
  })

  it('Part-tree test (relative --path)', async () => {
    test(['webpage-src'], 'webpage-expected/people', 'people')
    await checkLinks('webpage-expected/people', 'index.html')
  })

  it('Two-tree test', async () => {
    test(['mergetrees-src', 'webpage-src'], 'mergetrees-expected')
    await checkLinks('mergetrees-expected', 'index.html')
  })

  it('Absolute --path', async () => {
    test(
      ['webpage-src/people/adam'],
      'absolute-build-path-expected.txt',
      path.join(process.cwd(), 'absolute-build-path.nancy.txt'),
    )
  })

  it('Test nested macro invocations', () => {
    test(['nested-macro-src'], 'nested-macro-expected')
  })

  it('Failing executable test', () => {
    failingTest(['false.nancy.txt'], 'Command failed with exit code 1')
  })

  it('Passing executable test', () => {
    test(['true.nancy.txt'], 'true-expected.txt')
  })

  it('Executable test', () => {
    test(['page-template-with-date-src'], 'page-template-with-date-expected')
  })

  it('Test that macros aren\'t expanded in Nancy\'s command-line arguments', () => {
    test(['$path-src'], '$path-expected')
  })

  it('Test that $paste doesn\'t expand macros', () => {
    test(['paste-src'], 'paste-expected')
  })

  it('Test that $include with no arguments gives an error', () => {
    failingTest(['include-no-arg.nancy.txt'], '$include expects at least one argument')
  })

  it('Test that $paste with no arguments gives an error', () => {
    failingTest(['paste-no-arg.nancy.txt'], '$paste expects at least one argument')
  })

  it('Test escaping a macro without arguments', () => {
    test(['escaped-path-src'], 'escaped-path-expected')
  })

  it('Test escaping a macro with arguments', () => {
    test(['escaped-include-src'], 'escaped-include-expected')
  })

  it('Cookbook web site example', async () => {
    test(['cookbook-example-website-src'], 'cookbook-example-website-expected')
    await checkLinks('cookbook-example-website-expected', 'index/index.html')
  })

  it('Empty input path should cause an error', () => {
    failingTest([], 'at least one input must be given')
  })

  it('A non-existent input path should cause an error', () => {
    failingTest(['a'], "'' matches no path in the inputs")
  })

  it('$include-ing a non-existent file should give an error', () => {
    failingTest(['missing-include.nancy.txt'], 'cannot find \'foo\'')
  })

  it('Calling an undefined macro should give an error', () => {
    failingTest(['undefined-macro.nancy.txt'], 'no such macro \'$foo\'')
  })

  it('Calling an undefined single-letter macro should give an error', () => {
    failingTest(['undefined-short-macro.nancy.txt'], 'no such macro \'$f\'')
  })

  it('A macro call with a missing close brace should give an error', () => {
    failingTest(['missing-close-brace.nancy.txt'], 'missing close brace')
  })

  // CLI tests
  it('--help should produce output', async () => {
    const proc = run(['--help'])
    const {stdout} = await proc
    expect(stdout).to.contain('A simple templating system.')
  })

  it('Missing command-line argument should cause an error', async () => {
    await failingCliTest([], 'the following arguments are required')
  })

  it('Invalid command-line argument should cause an error', async () => {
    await failingCliTest(['--foo', 'a'], 'unrecognized arguments: --foo')
  })

  it('Running on a non-existent path should cause an error (DEBUG=yes coverage)', async () => {
    process.env.DEBUG = 'yes'
    try {
      await failingCliTest(['a'], "'' matches no path in the inputs")
    } finally {
      delete process.env.DEBUG
    }
  })

  it('Running on something not a file or directory should cause an error', async () => {
    const server = net.createServer()
    const tempFile = temporaryFile()
    server.listen(tempFile)
    try {
      await failingCliTest([`${tempFile}`], 'is not a file or directory')
    } finally {
      server.close()
    }
  })

  it('Non-existent --path should cause an error', async () => {
    await failingCliTest(
      ['--path', 'nonexistent', 'webpage-src'],
      'matches no path in the inputs',
    )
  })

  it('Empty INPUT-PATH should cause an error', async () => {
    await failingCliTest([''], 'input path must not be empty')
  })
})
