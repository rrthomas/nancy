import {test} from '@oclif/test'
import fs from 'fs'
import {Writable} from 'stream'
import path from 'path'
import execa from 'execa'
import {ExecaChildProcess} from 'execa'
import {directory} from 'tempy'
import dirTree = require('directory-tree')
import chai from 'chai'
import chaiAsPromised from 'chai-as-promised'

chai.use(chaiAsPromised)
const expect = chai.expect
const assert = chai.assert

interface File {
  name: string;
  size: number;
  extension: string;
  path?: string;
  contents: string;
}

interface Directory {
  name: string;
  size: number;
  path?: string;
}

function dirTreeContents(filepath: string) {
  return dirTree(filepath, {},
    (item: File, filepath: string) => {
      item.path = undefined
      item.contents = fs.readFileSync(filepath, 'utf-8')
    },
    (item: Directory) => {
      if (item.name === path.basename(filepath)) {
        item.name = ''
      }
      item.path = undefined
    }
  )
}

const nancyCmd = '../bin/run'

async function pipeProc(proc: ExecaChildProcess) {
  // Repeat stdout & stderr so we get them in test logs
  const {stdout, stderr} = await proc
  console.log(stdout)
  console.error(stderr)
}

async function runNancy(args: string[], inputFile?: string) {
  const proc = execa(nancyCmd, args)
  if (inputFile !== undefined) {
    fs.createReadStream(inputFile).pipe(proc.stdin as Writable)
  }

  // Repeat nancy's stdout & stderr so we get them in test logs
  await proc
  pipeProc(proc)

  return proc
}

async function nancyTest(src: string, template: string, pages?: string[], inputFile?: string) {
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
      pipeProc(proc)
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
  const res = dirTreeContents(outputDir)
  fs.rmdirSync(outputDir, {recursive: true})
  return res
}

describe('nancy', function () {
  // The tests are rather slow, but not likely to hang.
  this.timeout(0)

  before(function () {
    process.chdir('test')
  })

  test
    .do(async () => {
      const proc = runNancy(['--help'])
      const {stdout} = await proc
      expect(stdout).to.contain('A simple templating system.')
    })
    .it('--help produces output')

  test
    .do(async () => {
      const output = await nancyTest(
        'webpage-src', 'template.html',
        ['index.html', 'people/index.html', 'people/adam.html', 'people/eve.html']
      )
      expect(output).to.deep.equal(dirTreeContents('webpage-expected'))
    })
    .it('One-tree test')

  test
    .do(async () => {
      // Can only test one page, as template only supplied once!
      const output = await nancyTest('webpage-src', '-', ['index.html'], 'webpage-src/template.html')
      expect(output).to.deep.equal(dirTreeContents('webpage-stdin-expected'))
    })
    .it('Test with template on stdin')

  test
    .do(async () => {
      const proc = runNancy(['--output=-', '--root=webpage-src', 'template.html', 'index.html'])
      const {stdout} = await proc
      expect(stdout).to.equal(fs.readFileSync('webpage-stdout-expected/index.html', 'utf-8'))
    })
    .it('Test with output on stdout')

  test
    .do(async () => {
      const proc = runNancy(['--root=webpage-src', 'template.html', 'index.html'])
      const {stdout} = await proc
      expect(stdout).to.equal(fs.readFileSync('webpage-stdout-expected/index.html', 'utf-8'))
    })
    .it('Test with output on stdout, with no --output argument')

  test
    .do(async () => {
      const output = await nancyTest('nested-macro-src', 'template.txt', [''])
      expect(output).to.deep.equal(dirTreeContents('nested-macro-expected'))
    })
    .it('Test nested macro invocations')

  test
    .do(async () => {
      const mergedDir = directory()
      await execa('./mergetrees', ['mergetrees-src:webpage-src', mergedDir])
      const output = await nancyTest(
        mergedDir, 'template.html',
        ['index.html', 'animals/index.html', 'animals/adam.html', 'animals/eve.html']
      )
      expect(output).to.deep.equal(dirTreeContents('mergetrees-expected'))
      fs.rmdirSync(mergedDir, {recursive: true})
    })
    .it('Two-tree test')

  test
    .it(
      'Failing executable test',
      () => assert.isRejected(nancyTest('.', 'false.txt', ['dummy']))
    )

  test
    .do(async () => {
      const output = await nancyTest('.', 'true.txt', [''])
      expect(output).to.deep.equal(dirTreeContents('true-expected'))
    })
    .it('Passing executable test')

  test
    .do(async () => {
      const output = await nancyTest('page-template-with-date-src', 'Page.md', ['Page.md'])
      expect(output).to.deep.equal(dirTreeContents('page-template-with-date-expected'))
    })
    .it('Executable test with in-tree executable')

  test
    .do(async () => {
      const output = await nancyTest('.', 'path.txt', ['$path.txt'])
      expect(output).to.deep.equal(dirTreeContents('dollar-path-expected'))
    })
    .it('Ensure that macros aren\'t expanded in Nancy\'s command-line arguments')

  test
    .do(async () => {
      const output = await nancyTest('paste-src', 'paste.txt', ['paste.txt'])
      expect(output).to.deep.equal(dirTreeContents('paste-expected'))
    })
    .it('Test that $paste doesn\'t expand macros')

  test
    .do(async () => {
      const output = await nancyTest('cookbook-example-website-src', 'template.html')
      expect(output).to.deep.equal(dirTreeContents('cookbook-example-website-expected'))
    })
    .it('Cookbook web site example')
})
