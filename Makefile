.PHONY: test selftest check build run docker-build docker-run

test:
	python3 -m unittest discover -s tests -v

selftest:
	python3 -m tideway.selftest

check: test selftest build

build:
	python3 -m compileall -q run.py tideway scripts tests

run:
	python3 run.py

docker-build:
	docker build -t tideway:local .

docker-run:
	docker run --rm -p 127.0.0.1:8787:8787 -v tideway-data:/app/data tideway:local
