from yaml import load, FullLoader


def load_from_yaml(file: str) -> dict:
    with open(file, 'r', encoding='utf-8') as f:
        return load(f, Loader=FullLoader)
