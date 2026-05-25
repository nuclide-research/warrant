.PHONY: install install-api test demo

install:
	pip install -e loop/ -e librarian/ -e agent/

install-api:
	pip install -e "loop/[api]" -e librarian/ -e agent/

test:
	python -m pytest loop/tests/ -q
	python -m pytest agent/tests/ -q
	python -m pytest librarian/tests/ -q

demo:
	warrant run \
		--config sample-library/demo-config.json \
		--direction "add a hello_world function that prints Hello from Warrant"
