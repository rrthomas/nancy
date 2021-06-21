module namespace nc = "https://github.com/rrthomas/nancy/raw/master/nancy.dtd";
declare variable $path as xs:string external;
declare %public function nc:path-from-root($relpath as xs:string) as xs:string {
  concat(string-join((for $_ in 1 to count(tokenize($path, '/')) return '..'), '/'), '/', $relpath)
};
