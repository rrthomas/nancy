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
	version=$$(grep version pyproject.toml | grep -o "[0-9.]\+") && \
	twine upload dist/* && \
	gh release create v$$version --title "Release v$$version" dist/* && \
	git pull --tags

loc:
	cloc nancy
	cloc tests/*.py

example:
	python -c "import webbrowser; webbrowser.open(\"file://`pwd`/tests/test-files/cookbook-example-website-expected/index/index.html\")"

.PHONY: dist build
