# Nancy Cookbook

See the [README](README.md) for installation and usage. The rest of this
document shows examples of its use.

## Generating a web site <a name="website-example"></a>

*Note: the techniques used here, and more, are bundled into a convenient
tool that builds on Nancy, called
[Linton](https://rrthomas.github.io/linton).*

Suppose a web site has the following page design:

![from top to bottom: logo, breadcrumb trail, navigation menu, page body](website.svg)

Most of the elements are the same on each page, but the breadcrumb trail has
to show the canonical path to each page, and the logo is bigger on the home
page, which is `index/index.html`.

Suppose further that the web site has the following structure, where each
line corresponds to a page:

```
├── Home page
$paste{sh,-c,build-aux/dirtree tests/test-files/cookbook-example-website-expected | sed -e 's/\.html//g' | grep -v index | grep -v \\.}
```

The basic page template looks something like this:

```
$paste{cat,tests/test-files/cookbook-example-website-src/template.in.html}
```

Making the menu an included file is not strictly necessary, but makes the
template easier to read. The pages will be laid out as follows:

```
$paste{build-aux/dirtree,tests/test-files/cookbook-example-website-expected}
```

The corresponding source files are laid out as follows. This may look a
little confusing at first, but note the similarity to the HTML pages, and
hold on for the explanation!

```
$paste{build-aux/dirtree,tests/test-files/cookbook-example-website-src}
```

Note that there is only one menu fragment (the main menu is the same for
every page), while each section has its own breadcrumb trail
(`breadcrumb.in.html`), and each page has its own content
(`main.in.html`).

Now consider how Nancy builds the page whose URL is
`Places/Vladivostok/index.html`. Assume the source files are in the
directory `source`. This page is built from
`source/Places/Vladivostok/index.nancy.html`, whose contents is
`$paste{cat,tests/test-files/cookbook-example-website-src/Places/Vladivostok/index.nancy.html}`. According to the rules given in the
[Operation](README.md#operation) section of the manual, Nancy will look
first for files in `source/Places/Vladivostok`, then in `source/places`, and
finally in `source`. Hence, the actual list of files used to assemble the
page is:

$paste{env,NANCY_TMPDIR=/tmp/cookbook-dest.$$,sh,-c,rm -rf ${NANCY_TMPDIR} && DEBUG="*" PYTHONPATH=. python -m nancy --path Places/Vladivostok tests/test-files/cookbook-example-website-src ${NANCY_TMPDIR} 2>&1 | grep Found | cut -d " " -f 4 | sort | uniq | sed -e 's|^'\''tests/test-files/cookbook-example-website-src\(.*\)'\''$|* `source\1`|' && rm -rf ${NANCY_TMPDIR}}

For the site’s index page, the file `index/logo.in.html` will be used for the
logo fragment, which can refer to the larger graphic desired.

The `breadcrumb.in.html` fragments, except for the top-level one, contain the
command

```
\$include{breadcrumb.in.html}
```

When expanding `source/Places/breadcrumb.in.html`, Nancy ignores that file,
since it is already expanding it, and goes straight to
`source/breadcrumb.in.html`. This means that the breadcrumb trail can be
defined recursively: each `breadcrumb.in.html` fragment includes all those
above it in the source tree.

This scheme, though simple, is surprisingly flexible; this example has
covered all the standard techniques for Nancy’s use.

### Building the site

The site is built by running Nancy on the `sources` directory:

```
nancy sources site
```

## Adding a date to a template using a program <a name="date-example"></a>

Given a simple page template, a datestamp can be added by using the `date`
command with `\$paste`:

```
$paste{sh,-c,sed -e 's|datetime(2016\\\,10\\\,12)|now()|' < tests/test-files/page-template-with-date-src/Page.nancy.md}
```

This gives a result looking something like:

```
$include{cat,tests/test-files/page-template-with-date-src/Page.nancy.md}
```

## Dynamically naming output files and directories according

Since output file and directory names are expanded from input names, you can use commands to determine the name of an output file or directory.

For example, given a file called `author.in.txt` containing the text `Jo Bloggs`, an input file in the same directory called `\$include{author.in.txt}.txt` would be called `Jo Bloggs.txt` in the output.

## Adding code examples to Markdown
[FIXME]: # (Explain the techniques)

Look at the [source](Cookbook.nancy.md) for the Cookbook to see how Nancy is
used to include example source code, and the output of other commands, such
as directory listings.

[FIXME]: # (Mention more applications (invoice, python-package-template))
