.PHONY: install test gui-smoke build clean

install:
	python -m pip install -e '.[dev]'

test:
	QT_QPA_PLATFORM=offscreen PYTHONPATH=. python -m pytest

gui-smoke:
	QT_QPA_PLATFORM=offscreen PYTHONPATH=. python scripts/gui_smoke.py
	QT_QPA_PLATFORM=offscreen PYTHONPATH=. python scripts/gui_open_image_smoke.py

build:
	python scripts/build.py

clean:
	rm -rf build dist *.spec .pytest_cache artifacts/*.img artifacts/*.iso artifacts/*.pyz artifacts/*.png
