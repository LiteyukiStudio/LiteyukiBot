import pymongo


mc = pymongo.MongoClient("mongodb://localhost:27017")
mydb = mc["runoobdb"]
mndb = mc["liteyuki"]
mncol = mndb["users"]
mncol.insert_one({"quid": 114514, "luid": 1919810})