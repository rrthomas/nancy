import assert from 'assert'
import {IFS} from 'unionfs/lib/fs'
import path from 'path'
import execa from 'execa'
import slimdom from 'slimdom'
import {sync as parseXML} from 'slimdom-sax-parser'
import formatXML from 'xml-formatter'
import {
  evaluateXPath, evaluateXPathToNodes, evaluateXPathToFirstNode, evaluateXPathToString,
  registerCustomXPathFunction, registerXQueryModule, Options,
} from 'fontoxpath'
import {Expander, replacePathPrefix} from './expander'
import Debug from 'debug'

const debug = Debug('nancy-xml')

const nc = 'https://github.com/rrthomas/nancy/raw/master/nancy.dtd'
const dirtree = 'https://github.com/rrthomas/nancy/raw/master/dirtree.dtd'
const URI_BY_PREFIX: {[key: string]: string} = {nc, dirtree}

const xQueryOptions: Options = {
  namespaceResolver: (prefix: string) => URI_BY_PREFIX[prefix],
  language: evaluateXPath.XQUERY_3_1_LANGUAGE,
}

type XQueryResult = slimdom.Node[] | slimdom.Node | string[] | string | null

function xQueryResultIsNodeArray(res: XQueryResult): res is slimdom.Node[] {
  if (!Array.isArray(res)) {
    return false
  }
  if (res.length > 0) {
    return res[0] instanceof slimdom.Node
  }
  return true
}

function xQueryResultIsStringArray(res: XQueryResult): res is string[] {
  if (!Array.isArray(res)) {
    return false
  }
  if (res.length > 0) {
    return typeof res[0] === 'string' || res[0] instanceof String
  }
  return true
}

function xQueryResultIsNode(res: XQueryResult): res is slimdom.Node {
  return res instanceof slimdom.Node
}

function xQueryResultIsString(res: XQueryResult): res is string {
  return typeof res === 'string' || res instanceof String

}

export class XMLExpander extends Expander {
  private absInput: string

  private xtree: slimdom.Document

  constructor(input: string, output: string, filePath?: string, abortOnError?: boolean, inputFs?: IFS) {
    super(input, output, filePath, abortOnError, inputFs)
    this.absInput = path.resolve(input)
    this.xtree = this.dirTreeToXML(input)
  }

  private dirTreeToXML(root: string) {
    const xtree = new slimdom.Document()
    const objToNode = (obj: string) => {
      const stats = this.inputFs.statSync(obj)
      const parsedPath = path.parse(obj)
      const basename = (/^[^.]*/.exec(parsedPath.name) as string[])[0]
      let elem: slimdom.Element
      if (stats.isDirectory()) {
        elem = xtree.createElementNS(dirtree, 'directory')
        elem.setAttributeNS(dirtree, 'type', 'directory')
        const dir = this.inputFs.readdirSync(obj, {withFileTypes: true})
          .filter(dirent => dirent.name[0] !== '.')
        const dirs = dir.filter(dirent => dirent.isDirectory()).sort((a, b) => a.name.localeCompare(b.name))
        const files = dir.filter(dirent => !(dirent.isDirectory())).sort((a, b) => a.name.localeCompare(b.name))
        dirs.forEach((dirent) => elem.appendChild(objToNode(path.join(obj, dirent.name))))
        files.forEach((dirent) => elem.appendChild(objToNode(path.join(obj, dirent.name))))
      } else if (stats.isFile()) {
        if (this.isExecutable(obj)) {
          registerCustomXPathFunction(
            {localName: basename.replace(Expander.noCopyRegex, ''), namespaceURI: nc},
            // FIXME: 'array(xs:string)' unsupported: https://github.com/FontoXML/fontoxpath/issues/360
            ['array(*)'], 'xs:string',
            (_, args: string[]): string => {
              try {
                return execa.sync(path.join(this.absInput, replacePathPrefix(obj, this.input)), args).stdout
              } catch (error) {
                if (this.abortOnError) {
                  throw error
                }
                return `${error}`
              }
            },
          )
          elem = xtree.createElementNS(dirtree, 'executable')
        } else if (['.xml', '.xhtml'].includes(parsedPath.ext)) {
          const text = this.inputFs.readFileSync(obj, 'utf-8')
          const wrappedText = `<${basename}>${text}</${basename}>`
          let doc
          try {
            doc = parseXML(wrappedText, {additionalNamespaces: URI_BY_PREFIX})
          } catch (error) {
            throw new Error(`error parsing '${obj}': ${error}`)
          }
          assert(doc.documentElement !== null)
          elem = doc.documentElement
        } else {
          if (/.xq[lmy]?/.test(parsedPath.ext)) {
            registerXQueryModule(this.inputFs.readFileSync(obj, 'utf-8'));
            // FIXME: Parse namespace declaration in module?
            xQueryOptions.moduleImports = {nc}
          }
          elem = xtree.createElementNS(dirtree, 'file')
        }
        elem.setAttributeNS(dirtree, 'type', 'file')
      } else {
        elem = xtree.createElement('unknown')
      }
      elem.setAttributeNS(dirtree, 'path', obj)
      elem.setAttributeNS(dirtree, 'name', parsedPath.base)
      return elem
    }
    const rootElem = objToNode(root)
    xtree.appendChild(rootElem)
    debug(formatXML(slimdom.serializeToWellFormedString(xtree)))
    return xtree
  }

  private nodesToText(nodes: slimdom.Node[]): string {
    let res = ''
    for (const node of nodes) {
      res += slimdom.serializeToWellFormedString(node)
    }
    return res
  }

  private nodePath(elem: slimdom.Node) {
    const filePath = []
    for (
      let n: slimdom.Node | null = elem;
      n !== null && n !== this.xtree.documentElement;
      n = n.parentNode
    ) {
      const e = n as slimdom.Element
      filePath.unshift(e.getAttributeNS(dirtree, 'name') || e.nodeName)
    }
    return filePath.join(path.sep)
  }

  expandFile(baseFile: string): string {
    const xQueryVariables = {
      // FIXME: Put these variables in nc namespace.
      // See https://github.com/FontoXML/fontoxpath/issues/381
      root: this.input,
      path: replacePathPrefix(path.dirname(baseFile), this.input)
        .replace(Expander.templateRegex, '.'),
    }

    const queryAny = (xQuery: string, node: slimdom.Node): slimdom.Node[] | slimdom.Node |  string[] | string => {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
      const res = evaluateXPath(xQuery, node, null, xQueryVariables, evaluateXPath.ANY_TYPE, xQueryOptions)
      if (xQueryResultIsNode(res)) {
        return [res]
      } else if (xQueryResultIsString(res)) {
        return res
      } else if (xQueryResultIsNodeArray(res)) {
        return res
      } else if (xQueryResultIsStringArray(res)) {
        return res
      }
      throw new Error(`Result of query '${xQuery}' is not node list or string`)
    }

    // FIXME: annotate error with location
    const query = (xQuery: string, node: slimdom.Node): slimdom.Node[] | null => {
      return evaluateXPathToNodes(xQuery, node, null, xQueryVariables, xQueryOptions)
    }

    // FIXME: annotate error with location
    const queryFirst = (xQuery: string, node: slimdom.Node): slimdom.Node | null => {
      return evaluateXPathToFirstNode(xQuery, node, null, xQueryVariables, xQueryOptions)
    }

    // FIXME: annotate error with location
    const queryString = (xQuery: string, node: slimdom.Node): string => {
      return evaluateXPathToString(xQuery, node, null, xQueryVariables, xQueryOptions)
    }

    const index = (filePath: string) => {
      const components = replacePathPrefix(filePath, path.dirname(this.input)).split(path.sep)
      const xPathComponents = components.map((c) => `*[@dirtree:name="${c}"]`)
      const query = '/' + xPathComponents.join('/')
      return queryFirst(query, this.xtree)
    }

    const anchor = index(baseFile) as slimdom.Element
    if (anchor === null) {
      throw new Error(`path '${this.path}' does not exist in '${this.input}'`)
    }

    const expandNode = (elem: slimdom.Element, stack: slimdom.Node[]): slimdom.Node[] => {
      const findMatch = (xQuery: string): slimdom.Node => {
        const match = queryAny(`ancestor::dirtree:directory/${xQuery}`, anchor)
        if (xQueryResultIsNodeArray(match)) {
          for (const matchElem of match) {
            if (!stack.includes(matchElem)) {
              return matchElem
            }
          }
        } else if (xQueryResultIsNode(match)) {
          if (!stack.includes(match)) {
            return match
          }
        } else if (xQueryResultIsStringArray(match)) {
          return new slimdom.Text(match.join('\n'))
        } else if (match !== null) {
          return new slimdom.Text(match)
        }
        throw new Error(`${xQuery} not found for ${this.nodePath(elem)}`)
      }

      // Copy element to be expanded, and find queries
      const resElem = elem.cloneNode(true)
      const queries = query('descendant::nc:*', resElem) as slimdom.Element[]
      const attrQueries = query(`descendant::*[@*[namespace-uri()="${nc}"]]`, resElem) as slimdom.Element[]

      // Process element queries
      for (const queryElem of queries) {
        let expandedNodes
        try {
          const query = queryElem.innerHTML
          switch (queryElem.localName) {
            case 'include':
            case 'x':
              {
                const match = findMatch(query)
                if (match.nodeType !== slimdom.Node.ELEMENT_NODE) {
                  throw new Error(`Unexpected node type ${match.nodeType} returned for '${query}'`)
                }
                expandedNodes = expandNode(match as slimdom.Element, stack.concat(match))
              }
              break
            case 'paste':
              {
                const match = findMatch(query)
                if (match.nodeType !== slimdom.Node.ELEMENT_NODE) {
                  throw new Error(`Unexpected node type ${match.nodeType} returned for '${query}'`)
                }
                expandedNodes = [match]
              }
              break
            case 'do':
              {
                const match = queryAny(query, anchor)
                if (xQueryResultIsNodeArray(match)) {
                  expandedNodes = match.map((node) => expandNode(node as slimdom.Element, stack)).flat()
                } else if (xQueryResultIsStringArray(match)) {
                  expandedNodes = [new slimdom.Text(match.join('\n'))]
                } else if (xQueryResultIsNode(match)) {
                  expandedNodes = expandNode(match as slimdom.Element, stack)
                } else {
                  expandedNodes = [new slimdom.Text(match)]
                }
                break
              }
            default:
              debug(`No such macro ${queryElem.localName}`)
              throw new Error('no such macro')
          }
        } catch (error) {
          if (this.abortOnError) {
            throw error
          }
          if (typeof error === 'string') {
            queryElem.setAttributeNS(nc, 'error', error)
          } else if (error instanceof Error) {
            queryElem.setAttributeNS(nc, 'error', `${error.message}`)
          }
        }
        if (expandedNodes !== undefined) {
          queryElem.replaceWith(...expandedNodes)
        }
      }

      // Process attribute queries
      for (const queryElem of attrQueries) {
        const attrs = query(`./@*[namespace-uri()="${nc}"]`, queryElem) as slimdom.Attr[]
        for (const attr of attrs) {
          queryElem.removeAttributeNS(nc, attr.localName)

          registerCustomXPathFunction(
            {localName: 'include', namespaceURI: nc},
            ['xs:string'], 'xs:string',
            (_, query: string): string => {
              try {
                const match = findMatch(query)
                return this.nodesToText(expandNode(match as slimdom.Element, stack.concat(match)))
              } catch (error) {
                if (this.abortOnError) {
                  throw error
                }
                return `${error}`
              }
            },
          )
          registerCustomXPathFunction(
            {localName: 'paste', namespaceURI: nc},
            ['xs:string'], 'xs:string',
            (_, query: string): string => {
              try {
                return this.nodesToText([findMatch(query)])
              } catch (error) {
                if (this.abortOnError) {
                  throw error
                }
                return `${error}`
              }
            }
          )

          try {
            const expandedText = queryString(attr.value, anchor)
            queryElem.setAttribute(attr.localName, expandedText)
          } catch (error) {
            if (this.abortOnError) {
              throw error
            }
            queryElem.setAttributeNS(nc, attr.localName, `${error}`)
          }
        }
      }

      return resElem.childNodes
    }

    return this.nodesToText(expandNode(anchor, [anchor]))
  }
}
