.PHONY: build deploy

build:
	python3 convert.py

deploy: build
	bash scripts/deploy.sh
