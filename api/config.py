import os
from rdflib import Graph, Namespace, BNode
from rdflib.namespace import RDF, RDFS
from rdflib.plugins.stores.sparqlstore import SPARQLStore


APP_DIR = os.environ.get("APP_DIR", os.path.dirname(os.path.realpath(__file__)))
TEMPLATES_DIR = os.environ.get("TEMPLATES_DIR", os.path.join(APP_DIR, "view", "templates"))
STATIC_DIR = os.environ.get("STATIC_DIR", os.path.join(APP_DIR, "view", "style"))
LOGFILE = os.environ.get("LOGFILE", os.path.join(APP_DIR, "ogcapild.log"))
DEBUG = os.environ.get("DEBUG", True)
PORT = os.environ.get("PORT", 5000)
CACHE_HOURS = os.environ.get("CACHE_HOURS", 1)
CACHE_FILE = os.environ.get("CACHE_DIR", os.path.join(APP_DIR, "cache", "DATA.pickle"))
LOCAL_URIS = os.environ.get("LOCAL_URIS", True)

GEO = Namespace("http://www.opengis.net/ont/geosparql#")
GEOX = Namespace("https://linked.data.gov.au/def/geox#")
OGCAPI = Namespace("https://data.surroundaustralia.com/def/ogcapi/")
LANDING_PAGE_URL = "http://localhost:5000"
API_TITLE = "OGC LD API"
VERSION = "1.1"

DATASET_URI = "https://w3id.org/dggs/tb16pix"


def get_graph():
    from pathlib import Path
    import pickle
    import logging

    # try to load static data from a pickle file
    data_file = Path(APP_DIR).parent / "data" / "cache.pickle"
    logging.debug(data_file)
    if Path.is_file(data_file):
        logging.debug("loading g from cache")
        with open(data_file, 'rb') as f:
            g = pickle.load(f)
    else:
        logging.debug("no cache - reloading g from source files")
        g = Graph()
        g.parse(Path(APP_DIR).parent / "data" / "collections.ttl")
        g.parse(Path(APP_DIR).parent / "data" / "conformance_targets.ttl")
        g.parse(Path(APP_DIR).parent / "data" / "dataservice.ttl")
        g.parse(Path(APP_DIR).parent / "data" / "dataset.ttl")

        with open(data_file, 'wb') as f:
            pickle.dump(g, f)

    return g


# rHealPix
from rhealpixdggs.dggs import *
from rhealpixdggs.ellipsoids import *
WGS84_TB16 = Ellipsoid(a=6378137.0, b=6356752.314140356, e=0.0578063088401, f=0.003352810681182, lon_0=-131.25)
TB16Pix = RHEALPixDGGS(ellipsoid=WGS84_TB16, north_square=0, south_square=0, N_side=3)
