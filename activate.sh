

source ./cs182_venv/bin/activate

python backend_api.py &
python ed_integration.py &

# python -m http.server 8565 &