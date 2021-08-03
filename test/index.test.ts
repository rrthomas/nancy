import util from 'util'
import fs from 'fs'
import path from 'path'
import execa from 'execa'
import {directory} from 'tempy'
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

async function nancyTest(inputPath: string, expected: string, buildPath?: string) {
  let outputDir = directory()
  let outputObj = path.join(outputDir, 'output')
  const args = [inputPath]
  if (buildPath) {
    args.push(`--path=${buildPath}`)
  }
  args.push(outputObj)
  await runNancy(args)
  assertFileObjEqual(outputObj, expected)
  fs.rmdirSync(outputDir, {recursive: true})

  outputDir = directory()
  outputObj = path.join(outputDir, 'output')
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
  // The tests are rather slow, but not likely to hang.
  this.timeout(10000)

  before(function () {
    process.chdir('test')
  })

  it('--help should produce output', async () => {
    const proc = runNancy(['--help'])
    const {stdout} = await proc
    expect(stdout).to.contain('A simple templating system.')
  })

  it('Whole-tree test', async () => {
    await nancyTest('webpage-src', 'webpage-expected')
    await checkLinks('webpage-expected', 'index.html')
  })

  it('Part-tree test', async () => {
    await nancyTest('webpage-src', 'webpage-expected/people', 'people')
    await checkLinks('webpage-expected/people', 'index.html')
  })

  it('Two-tree test', async () => {
    await nancyTest('mergetrees-src:webpage-src', 'mergetrees-expected')
    await checkLinks('mergetrees-expected', 'index.html')
  })

  it('Test nested macro invocations', async () => {
    await nancyTest('nested-macro-src', 'nested-macro-expected')
  })

  it('Failing executable test', async () => {
    return assert.isRejected(runNancy(['false.nancy.txt', 'dummy']))
  })

  it('Passing executable test', async () => {
    await nancyTest('true.nancy.txt', 'true-expected.txt')
  })

  it('Executable test', async () => {
    await nancyTest('page-template-with-date-src', 'page-template-with-date-expected')
  })

  it('Test that macros aren\'t expanded in Nancy\'s command-line arguments', async () => {
    await nancyTest('$path-src', '$path-expected')
  })

  it('Test that $paste doesn\'t expand macros', async () => {
    await nancyTest('paste-src', 'paste-expected')
  })

  it('Cookbook web site example', async () => {
    await nancyTest('cookbook-example-website-src', 'cookbook-example-website-expected')
    await checkLinks('cookbook-example-website-expected', 'index/index.html')
  })
})
