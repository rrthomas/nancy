# Makefile for Nancy

NANCY = bin/run

all: Cookbook.md

Cookbook.md: Cookbook.md.in $(NANCY)
	$(NANCY) --output $@ $< $@

website-example:
	cd test && \
	mkdir website-example && \
	cp -a cookbook-example-website-assets/* cookbook-example-website-expected/* website-example/ && \
	xdg-open file://`pwd`/website-example/index.html
