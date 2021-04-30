import util from 'util'
import fs from 'fs'
import {Writable} from 'stream'
import path from 'path'
import execa from 'execa'
import {directory} from 'tempy'
import {compareSync} from 'dir-compare'
import chai from 'chai'
import chaiAsPromised from 'chai-as-promised'

chai.use(chaiAsPromised)
const expect = chai.expect
const assert = chai.assert

const nancyCmd = '../bin/run'

async function runNancy(args: string[], inputFile?: string) {
  const proc = execa(nancyCmd, args)
  if (inputFile !== undefined) {
    fs.createReadStream(inputFile).pipe(proc.stdin as Writable)
  }
  return proc
}

async function nancyTest(src: string, expected: string, template: string, pages?: string[], inputFile?: string) {
  const outputDir = directory()
  if (pages === undefined) {
    const cmd = './build-tree.ts'
    try {
      process.env.NANCY = nancyCmd
      const proc = execa(cmd, [src, template, outputDir])
      if (inputFile !== undefined) {
        fs.createReadStream(inputFile).pipe(proc.stdin as Writable)
      }
      await proc
    } catch (error) {
      throw new Error(`Test in \`${src}' failed to run: ${error}`)
    }
  } else {
    const results = []
    for (const page of pages) {
      const dir = path.join(outputDir, page === '' ? 'output.txt' : page)
      fs.mkdirSync(path.dirname(dir), {recursive: true})
      try {
        results.push(runNancy(['--verbose', `--root=${src}`, `--output=${dir}`, template, page], inputFile))
      } catch (error) {
        throw new Error(`Test in \`${src}' failed to run: ${error}`)
      }
    }
    await Promise.all(results)
  }
  const compareResult = compareSync(outputDir, expected, {compareContent: true})
  assert(compareResult.same, util.inspect(compareResult.diffSet))
  fs.rmdirSync(outputDir, {recursive: true})
}

describe('nancy', function () {
  // The tests are rather slow, but not likely to hang.
  this.timeout(0)

  before(function () {
    process.chdir('test')
  })

  it('--help should produce output', async () => {
    const proc = runNancy(['--help'])
    const {stdout} = await proc
    expect(stdout).to.contain('A simple templating system.')
  })

  it('One-tree test', async () => {
    await nancyTest(
      'webpage-src', 'webpage-expected', 'template.html',
      ['index.html', 'people/index.html', 'people/adam.html', 'people/eve.html'],
    )
  })

  it('Test with template on stdin', async () => {
    // Can only test one page, as template only supplied once!
    await nancyTest('webpage-src', 'webpage-stdin-expected', '-', ['index.html'], 'webpage-src/template.html')
  })

  it('Test with output on stdout', async () => {
    const proc = runNancy(['--output=-', '--root=webpage-src', 'template.html', 'index.html'])
    const {stdout} = await proc
    expect(stdout).to.equal(fs.readFileSync('webpage-stdout-expected/index.html', 'utf-8'))
  })

  it('Test with output on stdout, with no --output argument', async () => {
    const proc = runNancy(['--root=webpage-src', 'template.html', 'index.html'])
    const {stdout} = await proc
    expect(stdout).to.equal(fs.readFileSync('webpage-stdout-expected/index.html', 'utf-8'))
  })

  it('Test nested macro invocations', async () => {
    await nancyTest('nested-macro-src', 'nested-macro-expected', 'template.txt', [''])
  })

  it('Two-tree test', async () => {
    const mergedDir = directory()
    await execa('./mergetrees', ['mergetrees-src:webpage-src', mergedDir])
    await nancyTest(
      mergedDir, 'mergetrees-expected', 'template.html',
      ['index.html', 'animals/index.html', 'animals/adam.html', 'animals/eve.html']
    )
    fs.rmdirSync(mergedDir, {recursive: true})
  })

  it('Failing executable test', async () => {
    return assert.isRejected(nancyTest('.', 'dummy', 'false.txt', ['dummy']))
  })

  it('Passing executable test', async () => {
    await nancyTest('.', 'true-expected', 'true.txt', [''])
  })

  it('Executable test with in-tree executable', async () => {
    await nancyTest('page-template-with-date-src', 'page-template-with-date-expected', 'Page.md', ['Page.md'])
  })

  it('Ensure that macros aren\'t expanded in Nancy\'s command-line arguments', async () => {
    await nancyTest('.', 'dollar-path-expected', 'path.txt', ['$path.txt'])
  })

  it('Test that $paste doesn\'t expand macros', async () => {
    await nancyTest('paste-src', 'paste-expected', 'paste.txt', ['paste.txt'])
  })

  it('Cookbook web site example', async () => {
    await nancyTest('cookbook-example-website-src', 'cookbook-example-website-expected', 'template.html')
  })
})
