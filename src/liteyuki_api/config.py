import os.path

class Path:
    root = os.path.abspath(os.path.join(__file__, "../../../.."))
    src = os.path.join(root, "src")
    config = os.path.join(src, "config")
    data = os.path.join(src, "data")
