PY ?= .venv/bin/python
export PYTHONPATH := src

.PHONY: setup data build writeup test app all clean

setup:            ## create the virtualenv and install dependencies
	python3 -m venv .venv && $(PY) -m pip install -q -r requirements-dev.txt

build:            ## download UCI, simulate demo, load GA4 export if present, build marts and run checks
	$(PY) -m funnel_analytics.pipeline

writeup:          ## regenerate the auto-drafted write-ups
	$(PY) -m funnel_analytics.writeup --dataset uci
	-$(PY) -m funnel_analytics.writeup --dataset ga4

test:
	$(PY) -m pytest -q

app:
	$(PY) -m streamlit run app/streamlit_app.py

all: build test writeup

clean:
	rm -rf data/warehouse data/marts docs/*_auto.md
