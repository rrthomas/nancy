declare module 'strip-final-newline' {
  export default stripFinalNewline
  export function stripFinalNewline(input: string): string
  export function stripFinalNewline(input: Buffer): Buffer
}
