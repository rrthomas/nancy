# Makefile for maintainer tasks

build:
	python -m build

docs:
	PYTHONPATH=. python -m nancy README.nancy.md README.md && \
	PYTHONPATH=. python -m nancy Cookbook.nancy.md Cookbook.md

dist:
	git diff --exit-code && \
	rm -rf ./dist && \
	mkdir dist && \
	$(MAKE) build

test:
	tox

release:
	$(MAKE) test && \
	$(MAKE) dist && \
	twine upload dist/* && \
	gh release create v$$version --title "Release v$$version" dist/*

loc:
	cloc nancy tests/*.py

example:
	python -c "import webbrowser; webbrowser.open(\"file://`pwd`/tests/test-files/cookbook-example-website-expected/index/index.html\")"

.PHONY: dist build
