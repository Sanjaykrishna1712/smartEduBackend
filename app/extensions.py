# app/extensions.py
from flask_pymongo import PyMongo
from flask_cors import CORS
from flask_marshmallow import Marshmallow

mongo = PyMongo()
cors = CORS()
ma = Marshmallow()