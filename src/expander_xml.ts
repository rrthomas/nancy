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
const URI_BY_PREFIX: {[key: string]: string} = {nc}

const xQueryOptions: Options = {
  namespaceResolver: (prefix: string) => URI_BY_PREFIX[prefix],
  language: evaluateXPath.XQUERY_3_1_LANGUAGE,
}

function nodesToText(nodes: slimdom.Node[]): string {
  let res = ''
  for (const node of nodes) {
    res += slimdom.serializeToWellFormedString(node)
  }
  return res
}

type XQueryResult = slimdom.Node[] | slimdom.Node | string | null

function xQueryResultIsNodeArray(res: XQueryResult): res is slimdom.Node[] {
  if (!Array.isArray(res)) {
    return false
  }
  if (res.length > 0) {
    return res[0] instanceof slimdom.Node
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
        elem = xtree.createElementNS(nc, 'directory')
        elem.setAttributeNS(nc, 'type', 'directory')
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
                debug(`running ${this.input} ${obj}`)
                return execa.sync(path.join(this.absInput, replacePathPrefix(obj, this.input)), args).stdout
              } catch (error) {
                if (this.abortOnError) {
                  throw error
                }
                return `${error}`
              }
            },
          )
          elem = xtree.createElementNS(nc, 'executable')
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
            xQueryOptions.moduleImports = URI_BY_PREFIX
          }
          elem = xtree.createElementNS(nc, 'file')
        }
        elem.setAttributeNS(nc, 'type', 'file')
      } else {
        elem = xtree.createElement('unknown')
      }
      elem.setAttributeNS(nc, 'path', obj)
      elem.setAttributeNS(nc, 'name', parsedPath.base)
      return elem
    }
    const rootElem = objToNode(root)
    xtree.appendChild(rootElem)
    debug(formatXML(slimdom.serializeToWellFormedString(xtree)))
    return xtree
  }

  private nodePath(elem: slimdom.Element) {
    const filePath = []
    for (
      let n: slimdom.Node | null = elem;
      n !== null && n !== this.xtree.documentElement;
      n = n.parentNode
    ) {
      const e = n as slimdom.Element
      filePath.unshift(e.getAttributeNS(nc, 'name') || e.nodeName)
    }
    return filePath.join(path.sep)
  }

  expandFile(baseFile: string): string {
    const xQueryVariables = {
      // FIXME: Put these variables in nc namespace.
      root: this.input,
      path: replacePathPrefix(path.dirname(baseFile), this.input)
        .replace(Expander.templateRegex, '.'),
    }

    const queryAny = (xQuery: string, node: slimdom.Node): slimdom.Node[] | string => {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
      const res = evaluateXPath(xQuery, node, null, xQueryVariables, evaluateXPath.ANY_TYPE, xQueryOptions)
      if (xQueryResultIsNode(res)) {
        return [res]
      } else if (xQueryResultIsString(res)) {
        return res
      } else if (xQueryResultIsNodeArray(res)) {
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
      const xPathComponents = components.map((c) => `*[@nc:name="${c}"]`)
      const query = '/' + xPathComponents.join('/')
      return queryFirst(query, this.xtree)
    }

    const anchor = index(baseFile) as slimdom.Element
    if (anchor === null) {
      throw new Error(`path '${this.path}' does not exist in '${this.input}'`)
    }

    const expandNode = (elem: slimdom.Element, stack: slimdom.Node[]): slimdom.Node[] => {
      const findQueryMatch = (xQuery: string): slimdom.Node => {
        const match = queryAny(xQuery, anchor)
        if (xQueryResultIsNodeArray(match)) {
          for (const matchElem of match) {
            if (!stack.includes(matchElem)) {
              return matchElem
            }
          }
        } else if (match !== null) {
          return new slimdom.Text(match)
        }
        throw new Error(`${xQuery} not found for ${this.nodePath(elem)}`)
      }

      const findMatch = (xQuery: string): slimdom.Node =>
        findQueryMatch(`ancestor::nc:directory/${xQuery}`)

      // Copy element to be expanded, and find queries
      const resElem = elem.cloneNode(true)
      const queries = query('descendant::nc:*', resElem) as slimdom.Element[]
      const attrQueries = query(`descendant::*[@*[namespace-uri()="${nc}"]]`, resElem) as slimdom.Element[]

      // Process element queries
      for (const queryElem of queries) {
        let expandedNodes
        try {
          const query = queryElem.textContent ?? ''
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
                const match = findQueryMatch(query)
                switch (match.nodeType) {
                  case slimdom.Node.ELEMENT_NODE:
                    expandedNodes = [match]
                    break
                  case slimdom.Node.TEXT_NODE:
                    queryElem.textContent = match.textContent
                    break
                  default:
                    throw new Error(`Unexpected node type ${match.nodeType} returned for '${query}'`)
                }
                break
              }
            default:
              throw new Error('no such macro')
          }
        } catch (error) {
          if (this.abortOnError) {
            throw error
          }
          queryElem.setAttributeNS(nc, 'error', `${error}`)
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
                return nodesToText(expandNode(match as slimdom.Element, stack.concat(match)))
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
                return nodesToText([findMatch(query)])
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

    return nodesToText(expandNode(anchor, [anchor]))
  }
}
