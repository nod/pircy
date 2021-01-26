
DEV_VENV=./pyvenv

.DEFAULT_GOAL := dev

$(DEV_VENV): virtualenv


run:
	$(DEV_VENV)/bin/pircy run

sslkeys:
	mkdir -p keys
	openssl genrsa 4096 > keys/key
	openssl req -new -x509 -nodes -sha256 -days 365 -key keys/key > keys/cert

test:
	$(DEV_VENV)/bin/pytest

clean:
	rm -rf $(DEV_VENV)
	find . -type dir -name __pycache__ | xargs rm -rf
	find . -type dir -name pircy.egg-info | xargs rm -rf

virtualenv:
	python3 -m venv $(DEV_VENV)
	$(DEV_VENV)/bin/pip3 install -r requirements.txt

dev: $(DEV_VENV)
	# sets up this current dir to act as an importable python module
	$(DEV_VENV)/bin/pip3 install -e .


