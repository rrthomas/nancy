import util from 'util'
import fs from 'fs'
import path from 'path'
import net from 'net'
import {execa} from 'execa'
import {temporaryDirectory} from 'tempy'
import {compareSync, Difference} from 'dir-compare'
import {assert, expect} from 'chai'
import {check} from 'linkinator'

import {expand} from '../src/index.js'

const command = process.env.NODE_ENV === 'coverage' ? '../bin/test-run.sh' : '../bin/run.js'

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

function test(inputDirs: string[], expected: string, buildPath?: string, outputDir?: string) {
  let tmpDir
  let outputObj
  if (outputDir === undefined) {
    tmpDir = temporaryDirectory()
    outputObj = path.join(tmpDir, 'output')
  } else {
    outputObj = outputDir
  }
  try {
    if (buildPath !== undefined) {
      expand(inputDirs, outputObj, buildPath)
    } else {
      expand(inputDirs, outputObj)
    }
    assertFileObjEqual(outputObj, expected)
  } finally {
    if (tmpDir !== undefined) {
      fs.rmSync(tmpDir, {recursive: true})
    }
  }
}

function failingTest(
  inputDirs: string[],
  expected: string,
  buildPath?: string,
  outputDir?: string,
) {
  const expectedDir = temporaryDirectory()
  try {
    test(inputDirs, expectedDir, buildPath, outputDir)
  } catch (error: any) {
    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
    expect(error.message).to.contain(expected)
    return
  } finally {
    fs.rmSync(expectedDir, {recursive: true})
  }
  throw new Error('test passed unexpectedly')
}

async function cliTest(args: string[], expected: string, outputDir?: string) {
  let tmpDir
  let outputObj
  if (outputDir === undefined) {
    tmpDir = temporaryDirectory()
    outputObj = path.join(tmpDir, 'output')
  } else {
    outputObj = outputDir
  }
  try {
    const res = await run(args.concat(outputObj))
    if (tmpDir !== undefined) {
      assertFileObjEqual(outputObj, expected)
    } else {
      expect(res.stdout).to.equal(fs.readFileSync(expected, 'utf-8'))
    }
  } finally {
    if (tmpDir !== undefined) {
      fs.rmSync(tmpDir, {recursive: true})
    }
  }
}

async function failingCliTest(args: string[], expected: string, outputDir?: string) {
  try {
    await cliTest(args, '', outputDir)
  } catch (error: any) {
    expect(error.stderr).to.contain(expected)
    return
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

  it('Test nested macro invocations', () => {
    test(['nested-macro-src'], 'nested-macro-expected')
  })

  it('Failing executable test', () => {
    failingTest([process.cwd()], 'Command failed with exit code 1', 'false.nancy.txt')
  })

  it('Passing executable test', () => {
    test([process.cwd()], 'true-expected.txt', 'true.nancy.txt')
  })

  it('Executable test', () => {
    test(['page-template-with-date-src'], 'page-template-with-date-expected')
  })

  it("Test that macros aren't expanded in Nancy's command-line arguments", () => {
    test(['$path-src'], '$path-expected')
  })

  it("Test that $paste doesn't expand macros", () => {
    test(['paste-src'], 'paste-expected')
  })

  it('Test that $include with no arguments gives an error', () => {
    failingTest([process.cwd()], '$include expects at least one argument', 'include-no-arg.nancy.txt')
  })

  it('Test that $paste with no arguments gives an error', () => {
    failingTest([process.cwd()], '$paste expects at least one argument', 'paste-no-arg.nancy.txt')
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

  it('Test expanding a file with relative includes', () => {
    test([process.cwd()], 'file-root-relative-include-expected.txt', 'file-root-relative-include.nancy.txt')
  })

  it('Empty input path should cause an error', () => {
    failingTest([], 'at least one input must be given')
  })

  it('A non-existent input path should cause an error', () => {
    failingTest(['a'], "input 'a' does not exist")
  })

  it('An input that is not a directory should cause an error', () => {
    failingTest(['random-text.txt'], "input 'random-text.txt' is not a directory")
  })

  it('$include-ing a non-existent file should cause an error', () => {
    failingTest([process.cwd()], "cannot find 'foo'", 'missing-include.nancy.txt')
  })

  it('Calling an undefined macro should cause an error', () => {
    failingTest([process.cwd()], "no such macro '$foo'", 'undefined-macro.nancy.txt')
  })

  it('Calling an undefined single-letter macro should cause an error', () => {
    failingTest([process.cwd()], "no such macro '$f'", 'undefined-short-macro.nancy.txt')
  })

  it('A macro call with a missing close brace should cause an error', () => {
    failingTest([process.cwd()], 'missing close brace', 'missing-close-brace.nancy.txt')
  })

  it('Trying to output multiple files to stdout should cause an error', async () => {
    failingTest(['webpage-src'], 'cannot output multiple files to stdout', undefined, '-')
  })

  // CLI tests
  it('--help should produce output', async () => {
    const proc = run(['--help'])
    const {stdout} = await proc
    expect(stdout).to.contain('A simple templating system.')
  })

  it('Running with a single file as INPUT-PATH should work', async () => {
    await cliTest(['file-root-relative-include.nancy.txt'], 'file-root-relative-include-expected.txt')
  })

  it('Output to stdout of a single file should work', async () => {
    await cliTest(['file-root-relative-include.nancy.txt'], 'file-root-relative-include-expected.txt', '-')
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
      await failingCliTest(['a'], "input 'a' does not exist")
    } finally {
      delete process.env.DEBUG
    }
  })

  it('Running on something not a file or directory should cause an error', async () => {
    const server = net.createServer()
    const tempDir = temporaryDirectory()
    const tempFile = path.join(tempDir, 'foo')
    server.listen(tempFile)
    try {
      await failingCliTest([`--path=${path.basename(tempFile)}`, tempDir], 'is not a file or directory')
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

  it('Absolute --path should cause an error', async () => {
    await failingCliTest(
      ['--path', '/nonexistent', 'webpage-src'],
      'build path must be relative',
    )
  })

  it('Output to subdirectory of input should cause an error', async () => {
    await failingCliTest(
      ['webpage-src'],
      'output cannot be in any input directory',
      'webpage-src/foo',
    )
  })

  it('Empty INPUT-PATH should cause an error', async () => {
    await failingCliTest([''], 'input path must not be empty')
  })
})
