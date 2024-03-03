from src.liteyuki import *


if __name__ == '__main__':
    liteyuki = Liteyuki()
    app = liteyuki.get_asgi()
    liteyuki.run(app="main:app")