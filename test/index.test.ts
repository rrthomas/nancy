import util from 'util'
import fs from 'fs'
import path from 'path'
import net from 'net'
import execa from 'execa'
import tempy from 'tempy'
import {compareSync, Difference} from 'dir-compare'
import chai from 'chai'
import chaiAsPromised from 'chai-as-promised'
import {check} from 'linkinator'

import {expand, unionFs} from '../src/index'

chai.use(chaiAsPromised)
const {expect} = chai
const {assert} = chai

const command = process.env.NODE_ENV === 'coverage' ? '../bin/test-run' : '../bin/run'

async function run(args: string[]) {
  return execa(command, args)
}

function diffsetDiffsOnly(diffSet: Difference[]): Difference[] {
  return diffSet.filter((diff) => diff.state !== 'equal')
}

function assertFileObjEqual(obj: string, expected: string) {
  const stats = fs.statSync(obj)
  if (stats.isDirectory()) {
    const compareResult = compareSync(obj, expected, {compareContent: true})
    assert(
      compareResult.same, util.inspect(diffsetDiffsOnly(compareResult.diffSet as Difference[])),
    )
  } else {
    assert(
      fs.readFileSync(obj).equals(fs.readFileSync(expected)),
      `'${obj}' does not match expected '${expected}'`,
    )
  }
}

function test(inputDirs: string[], expected: string, buildPath?: string) {
  const outputDir = tempy.directory()
  const outputObj = path.join(outputDir, 'output')
  if (inputDirs.length > 1) {
    expand(inputDirs[0], outputObj, buildPath, unionFs(inputDirs))
  } else if (buildPath !== undefined) {
    expand(inputDirs[0], outputObj, buildPath)
  } else {
    expand(inputDirs[0], outputObj)
  }
  assertFileObjEqual(outputObj, expected)
  fs.rmdirSync(outputDir, {recursive: true})
}

function failingTest(inputDirs: string[], expected: string) {
  try {
    test(inputDirs, 'dummy')
  } catch (error: any) {
    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
    expect(error.message).to.contain(expected)
    return
  }
  throw new Error('test passed unexpectedly')
}

async function failingCliTest(args: string[], expected: string) {
  try {
    await run(args)
  } catch (error: any) {
    // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
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

  it('Part-tree test', async () => {
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
    failingTest(['false.nancy.txt', 'dummy'], 'Command failed with exit code 1')
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
    failingTest(['include-no-arg.nancy.txt', 'dummy'], '$include expects at least one argument')
  })

  it('Test that $paste with no arguments gives an error', () => {
    failingTest(['paste-no-arg.nancy.txt', 'dummy'], '$paste expects at least one argument')
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
    failingTest([], 'The "path" argument must be of type string.')
  })

  it('A non-existent input path should cause an error', () => {
    failingTest(['a'], 'no such file or directory')
  })

  it('$include-ing a non-existent file should give an error', () => {
    failingTest(['missing-include.nancy.txt'], 'cannot find \'foo\'')
  })

  it('Calling an undefined macro should give an error', () => {
    failingTest(['undefined-macro.nancy.txt'], 'no such macro \'$foo\'')
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
    await failingCliTest(
      ['dummy'],
      'the following arguments are required',
    )
  })

  it('Invalid command-line argument should cause an error', async () => {
    await failingCliTest(
      ['--foo', 'a', 'b'],
      'unrecognized arguments: --foo',
    )
  })

  it('Running on a non-existent path should cause an error (DEBUG=yes coverage)', async () => {
    process.env.DEBUG = 'yes'
    await failingCliTest(
      ['a', 'b'],
      'no such file or directory',
    )
    delete process.env.DEBUG
  })

  it('Running on something not a directory or file should cause an error', async () => {
    const server = net.createServer()
    const tempFile = tempy.file()
    server.listen(tempFile)
    await failingCliTest(
      [`${tempFile}`, 'dummy'],
      'is not a directory or file',
    )
    server.close()
  })

  it('Non-existent --path should cause an error', async () => {
    await failingCliTest(
      ['--path', 'nonexistent', 'webpage-src', 'dummy'],
      'no such file or directory',
    )
  })

  it('Empty INPUT-PATH should cause an error', async () => {
    await failingCliTest(
      ['', 'dummy'],
      'input path must not be empty',
    )
  })
})
