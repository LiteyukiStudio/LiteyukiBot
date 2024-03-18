from yaml import load, FullLoader

config = None


def load_from_yaml(file: str) -> dict:
    global config
    with open(file, 'r', encoding='utf-8') as f:
        config = load(f, Loader=FullLoader)
        return config
