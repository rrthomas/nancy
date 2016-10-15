# Nancy Cookbook

See the [README](README.md) for installation and usage. The rest of this
document shows examples of its use.

## Generating a web site <a name="website-example"></a>

[FIXME]: # (Use a diagram below)
Suppose a web site has the following page design, from top to bottom: logo, breadcrumb trail, navigation menu, page body.

Most of the elements are the same on each page, but the breadcrumb trail has
to show the canonical path to each page, and the logo is bigger on the home
page, which is the default `index.html`.

Suppose further that the web site has the following structure, where each
line corresponds to a page:

    ├── People
    │   ├── Hilary Pilary
    │   └── Jo Bloggs
    ├── Places
    │   ├── Timbuktu
    │   └── Vladivostok
    └── Home page

The basic page template looks something like this:

    <!DOCTYPE html>
    <html>
      <head>
        <link rel="stylesheet" type="text/css" href="/style.css">
        <title>$include{title.txt}</title>
      </head>
      <body>
        <div class="wrapper">
          <div class="logo">$include{logo.html}</div>
          <div class="breadcrumb"><div class="breadcrumb-content">$include{breadcrumb.html}</div></div>
        </div>
        <div class="wrapper">
          <div class="menu">$include{menu.html}</div>
          <div class="main">$include{main.html}</div>
        </div>
      </body>
    </html>

Making the menu an included file is not strictly necessary, but makes the
template easier to read. The pages will be laid out as follows:

    ├── People
    │   ├── Hilary Pilary.html
    │   ├── index.html
    │   └── Jo Bloggs.html
    ├── Places
    │   ├── index.html
    │   ├── Timbuktu.html
    │   └── Vladivostok.html
    └── index.html

The corresponding source files will be laid out as follows. This may look a
little confusing at first, but note the similarity to the HTML pages, and
hold on for the explanation!

    ├── index.html
    │   ├── logo.html
    │   ├── main.html
    │   └── title.txt
    ├── People
    │   ├── Hilary Pilary.html
    │   │   ├── breadcrumb.html
    │   │   ├── main.html
    │   │   └── title.txt
    │   ├── index.html
    │   │   ├── main.html
    │   │   └── title.txt
    │   ├── Jo Bloggs.html
    │   │   ├── breadcrumb.html
    │   │   ├── main.html
    │   │   └── title.txt
    │   └── breadcrumb.html
    ├── Places
    │   ├── index.html
    │   │   ├── main.html
    │   │   └── title.txt
    │   ├── Timbuktu.html
    │   │   ├── breadcrumb.html
    │   │   ├── main.html
    │   │   └── title.txt
    │   ├── Vladivostok.html
    │   │   ├── breadcrumb.html
    │   │   ├── main.html
    │   │   └── title.txt
    │   └── breadcrumb.html
    ├── breadcrumb.html
    ├── logo.html
    ├── menu.html
    └── template.html

Note that there is only one menu fragment (the main menu is the same for
every page), while each section has its own breadcrumb trail
(`breadcrumb.html`), and each page has its own content
(`main.html`).

Now consider how Nancy builds the page whose URL is
`places/vladivostok.html`. Assume the source files are in the directory
`source`. According to the rules given in
the [Operation](README.md#operation) section of the manual, Nancy will look
first for files in `source/places/vladivostok.html`, then in
`source/places`, and finally in `source`. Hence, the actual list of files
used to assemble the page is:

[FIXME]: # (Generate this list)
* `source/template.html`
* `source/logo.html`
* `source/places/breadcrumb.html`
* `source/menu.html`
* `source/places/vladivostok.html/main.html`

For the site’s index page, the file `index.html/logo.html` will be used
for the logo fragment, which can refer to the larger graphic desired.

[FIXME]: # (Explain how to build the web site statically, or serve it dynamically.)

This scheme, though simple, is surprisingly flexible; this simple example
has covered all the standard techniques for Nancy’s use.

## Adding a date to a template using a program

Given a simple page template, a timestamp can be added by using the `date` command with `$paste`:

    # Title
    
    Page contents.
    
    --
    
    Last updated: $paste{date,+%Y-%m-%d}

This gives a result looking something like:

    # Title
    
    Page contents.
    
    --
    
    Last updated: 2016-10-12

## Adding code examples to Markdown
[FIXME]: # (Explain the techniques)

Look at the [source](Cookbook.md.in) for the Cookbook to see how Nancy is used to include example source code, and the output of other commands, such as directory listings.

[FIXME]: # (Add an example about uniquely numbered invoices)