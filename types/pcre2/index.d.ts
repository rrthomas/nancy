declare module 'pcre2' {
  export class PCRE2 {
    constructor (pattern: string, options: string)
    replace(string: string, replaceValue: string): string
    replace(string: string, replacer: function): string
  }
}
