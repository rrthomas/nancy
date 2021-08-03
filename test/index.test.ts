import util from 'util'
import fs from 'fs'
import path from 'path'
import net from 'net'
import execa from 'execa'
import tempy, {directory} from 'tempy'
import {compareSync, Difference} from 'dir-compare'
import chai from 'chai'
import chaiAsPromised from 'chai-as-promised'
import {check} from 'linkinator'

import {expand, unionFs} from '../src/index'

chai.use(chaiAsPromised)
const expect = chai.expect
const assert = chai.assert

const nancyCmd = process.env.NODE_ENV === 'coverage' ? '../bin/test-run' : '../bin/run'

async function runNancy(args: string[]) {
  return execa(nancyCmd, args)
}

function assertFileObjEqual(obj: string, expected: string) {
  const stats = fs.statSync(obj)
  if (stats.isDirectory()) {
    const compareResult = compareSync(obj, expected, {compareContent: true})
    assert(compareResult.same, util.inspect(diffsetDiffsOnly(compareResult.diffSet as Difference[])))
  } else {
    assert(
      fs.readFileSync(obj).equals(fs.readFileSync(expected)),
      `'${obj}' does not match expected '${expected}'`
    )
  }
}

function diffsetDiffsOnly(diffSet: Difference[]): Difference[] {
  return diffSet.filter((diff) => diff.state !== 'equal')
}

function nancyTest(inputPath: string, expected: string, buildPath?: string) {
  const outputDir = directory()
  const outputObj = path.join(outputDir, 'output')
  const inputDirs = inputPath.split(path.delimiter)
  expand(inputDirs[0], outputObj, buildPath, unionFs(inputDirs))
  assertFileObjEqual(outputObj, expected)
  fs.rmdirSync(outputDir, {recursive: true})
}

async function checkLinks(root: string, start: string) {
  const results = await check({path: start, serverRoot: root})
  if (!results.passed) {
    console.error(results)
  }
  assert(results.passed, 'Broken links in output')
}

describe('nancy', function () {
  // In coverage mode, allow for recompilation.
  this.timeout(10000)

  before(function () {
    process.chdir('test')
  })

  // Module tests
  it('Whole-tree test', async () => {
    nancyTest('webpage-src', 'webpage-expected')
    await checkLinks('webpage-expected', 'index.html')
  })

  it('Part-tree test', async () => {
    nancyTest('webpage-src', 'webpage-expected/people', 'people')
    await checkLinks('webpage-expected/people', 'index.html')
  })

  it('Two-tree test', async () => {
    nancyTest('mergetrees-src:webpage-src', 'mergetrees-expected')
    await checkLinks('mergetrees-expected', 'index.html')
  })

  it('Test nested macro invocations', () => {
    nancyTest('nested-macro-src', 'nested-macro-expected')
  })

  it('Failing executable test', () => {
    try {
      nancyTest('false.nancy.txt', 'dummy')
    } catch (error) {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
      expect(error.message).to.contain('Command failed with exit code 1')
    }
  })

  it('Passing executable test', () => {
    nancyTest('true.nancy.txt', 'true-expected.txt')
  })

  it('Executable test', () => {
    nancyTest('page-template-with-date-src', 'page-template-with-date-expected')
  })

  it('Test that macros aren\'t expanded in Nancy\'s command-line arguments', () => {
    nancyTest('$path-src', '$path-expected')
  })

  it('Test that $paste doesn\'t expand macros', () => {
    nancyTest('paste-src', 'paste-expected')
  })

  it('Cookbook web site example', async () => {
    nancyTest('cookbook-example-website-src', 'cookbook-example-website-expected')
    await checkLinks('cookbook-example-website-expected', 'index/index.html')
  })

  // CLI tests
  it('--help should produce output', async () => {
    const proc = runNancy(['--help'])
    const {stdout} = await proc
    expect(stdout).to.contain('A simple templating system.')
  })

  it('Missing command-line argument should cause an error', async () => {
    try {
      await runNancy(['dummy'])
    } catch (error) {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
      expect(error.stderr).to.contain('the following arguments are required')
    }
  })

  it('--foo should cause an error', async () => {
    try {
      await runNancy(['--foo', 'a', 'b'])
    } catch (error) {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
      expect(error.stderr).to.contain('unrecognized arguments: --foo')
    }
  })

  it('Running on a non-existent path should cause an error (DEBUG=yes coverage)', async () => {
    process.env.DEBUG = 'yes'
    try {
      await runNancy(['a', 'b'])
    } catch (error) {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
      expect(error.stderr).to.contain('no such file or directory')
    }
    delete process.env.DEBUG
  })

  it('Running on a non-existent path should cause an error', async () => {
    try {
      await runNancy(['a', 'b'])
    } catch (error) {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
      expect(error.stderr).to.contain('no such file or directory')
    }
  })

  it('Running on something not a directory or file should cause an error', async () => {
    const server = net.createServer()
    const tempFile = tempy.file()
    server.listen(tempFile)
    try {
      await runNancy([`${tempFile}`, 'dummy'])
    } catch (error) {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
      expect(error.stderr).to.contain('is not a directory or file')
    } finally {
      server.close()
    }
  })

  it('Non-existent --path should cause an error', async () => {
    try {
      await runNancy(['--path', 'nonexistent', 'webpage-src', 'dummy'])
    } catch (error) {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
      expect(error.stderr).to.contain('no such file or directory')
    }
  })
})
