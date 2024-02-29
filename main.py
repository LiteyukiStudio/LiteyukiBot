from src.liteyuki import *
from pymongo import MongoClient

a = MongoClient("mongodb://localhost:27017/")

if __name__ == '__main__':
    liteyuki = Liteyuki()
    app = liteyuki.get_asgi()
    liteyuki.run(app="main:app")
