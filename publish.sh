# NOTE: authentication is done using $HOME/.pypirc
# https://pypi.org/help/#apitoken

python3 -m twine check dist/*
python3 -m twine upload dist/*
