# Nancy Cookbook

See the [README](README.md) for installation and usage. The rest of this
document shows examples of its use.

## Generating a web site <a name="website-example"></a>
[FIXME]: # (Add example use of an executable fragment (date))
[FIXME]: # (Add an example about uniquely numbered invoices)
[FIXME]: # (The web page examples are unclear; really ought to be actual web pages with some sort of structure diagrams automatically generated)

Suppose a web site has the following page design, from top to bottom: logo,
navigation menu, breadcrumb trail, page body.

Most of the elements are the same on each page, but the breadcrumb trail has
to show the canonical path to each page, and the logo is bigger on the home
page, which is the default `index.html`.

Suppose further that the web site has the following structure, where each
line corresponds to a page:

* Home page
* People
    * Jo Bloggs
    * Hilary Pilary
    * \dots
* Places
    * Vladivostok
    * Timbuktu
    * \dots

The basic page template looks something like this:

    <html>
      <link href="style.css" rel="stylesheet" type="text/css">
      <title>$include{title}</title>
      <body>
        <div class="logo">$include{logo.html}</div>
        <div class="menu">$include{menu.html}</div>
        <div class="breadcrumb">$include{breadcrumb.html}</div>
        <div class="main">$include{main.html}</div>
      </body>
    </html>

Making the menu an included file is not strictly necessary, but makes the
template easier to read. The pages will be laid out as follows:

* `/`
    * `index.html`
    * `people/`
        * `index.html`
        * `jo_bloggs.html`
        * `hilary_pilary.html`
    * `places/`
        * `index.html`
        * `vladivostok.html`
        * `timbuktu.html`

The corresponding source files will be laid out as follows. This may look a
little confusing at first, but note the similarity to the HTML pages, and
hold on for the explanation!

* `source/`
    * `template.html` (the template shown above)
    * `menu.html`
    * `logo.html`
    * `breadcrumb.html`
    * `index.html/`
        * `main.html`
        * `logo.html`
    * `people/`
        * `breadcrumb.html`
        * `index.html/`
            * `main.html`
        * `jo_bloggs.html/`
            * `main.html`
        * `hilary_pilary.html/`
            * `main.html`
    * `places/`
        * `breadcrumb.html`
        * `index.html/`
            * `main.html`
        * `vladivostok.html/`
            * `main.html`
        * `timbuktu.html/`
            * `main.html`

Note that there is only one menu fragment (the main menu is the same for
every page), while each section has its own breadcrumb trail
(`breadcrumb.html`), and each page has its own content
(`main.html`).

Now consider how Nancy builds the page whose URL is `vladivostok.html`.
According to the rules given in the [Operation](README.md#operation) section
of the manual, Nancy will look first for files in
`source/places/vladivostok.html`, then in `source/places`, and finally in
`source`. Hence, the actual list of files used to assemble the page is:

* `source/template.html`
* `source/logo.html`
* `source/menu.html`
* `source/places/breadcrumb.html`
* `source/places/vladivostok.html/main.html`

For the site’s index page, the file `index.html/logo.html` will be used
for the logo fragment, which can refer to the larger graphic desired.

[FIXME]: # (Explain how to build the web site statically, or serve it dynamically.)

This scheme, though simple, is surprisingly flexible; this simple example
has covered all the standard techniques for Nancy’s use.
