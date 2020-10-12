import logging
from flask import (
    Flask,
    request,
    render_template,
    url_for,
    jsonify,
    Blueprint,
    Response
)
from flask_restx import Namespace, reqparse, Api, Resource
from api.config import *
from pyldapi import Renderer
from api.model import *
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCAT, DCTERMS, RDF

app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)

blueprint = Blueprint('api', __name__)


@app.route("/")
def landing_page():
    try:
        return LandingPageRenderer(request).render()
    except Exception as e:
        logging.debug(e)
        return Response(
            "The API cannot connect to its data source, Check your SPARQL endpoint (you gave {}) "
            "and the query".format(SPARQL_ENDPOINT),
            status=500,
            mimetype="text/plain"
        )


api = Api(app, doc="/doc/", version='1.0', title="OGC LD API",
          description="Open API Documentation for this {}".format(API_TITLE))
# sapi = Namespace('oai', description="Search from DGGS Engine", version="1.0")
# api.add_namespace(sapi)
app.register_blueprint(blueprint)


@app.context_processor
def context_processor():
    """
    A set of variables available globally for all Jinja templates.
    :return: A dictionary of variables
    :rtype: dict
    """
    MEDIATYPE_NAMES = {
        "text/html": "HTML",
        "application/json": "JSON",
        "application/geo+json": "GeoJSON",
        "text/turtle": "Turtle",
        "application/rdf+xml": "RDX/XML",
        "application/ld+json": "JSON-LD",
        "text/n3": "Notation-3",
        "application/n-triples": "N-Triples",
    }

    return dict(
        LOCAL_URIS=LOCAL_URIS,
        MEDIATYPE_NAMES=MEDIATYPE_NAMES,
        API_TITLE=API_TITLE,
    )


@api.route("/spec")
class Spec(Resource):
    def get(self):
        return api.__schema__


@api.route("/conformance")
class ConformanceRoute(Resource):
    def get(self):
        q = """
            PREFIX dcterms: <http://purl.org/dc/terms/>
            PREFIX ogcapi: <https://data.surroundaustralia.com/def/ogcapi/>
            
            SELECT *
            WHERE {
                ?uri a ogcapi:ConformanceTarget ;
                   dcterms:title ?title
            }
            """
        graph = get_graph()
        conformance_classes = []
        for s in graph.subjects(predicate=RDF.type, object=OGCAPI.ConformanceTarget):
            uri = str(s)
            for o in graph.objects(subject=s, predicate=DCTERMS.title):
                title = str(o)
            conformance_classes.append((uri, title))
        return ConformanceRenderer(request, conformance_classes).render()


@api.route("/collections")
class CollectionsRoute(Resource):
    def get(self):
        return CollectionsRenderer(request).render()


@api.route("/collections/<string:collection_id>")
@api.param("collection_id", "The ID of a Collection delivered by this API. See /collections for the list.")
class CollectionRoute(Resource):
    def get(self, collection_id):
        g = get_graph()
        # get the URI for the Collection using the ID
        collection_uri = None
        for s in g.subjects(predicate=DCTERMS.identifier, object=Literal(collection_id)):
            collection_uri = s

        if collection_uri is None:
            return Response(
                "You have entered an unknown Collection ID",
                status=400,
                mimetype="text/plain"
            )

        return CollectionRenderer(request, collection_uri).render()


@api.route("/collections/<string:collection_id>/items")
@api.param("collection_id", "The ID of a Collection delivered by this API. See /collections for the list.")
class FeaturesRoute(Resource):
    def get(self, collection_id):
        return FeaturesRenderer(request, collection_id).render()


@api.route("/collections/<string:collection_id>/items/<string:item_id>")
@api.param("collection_id", "The ID of a Collection delivered by this API. See /collections for the list.")
@api.param("item_id", "The ID of a Feature in this Collection's list of Items")
class FeatureRoute(Resource):
    def get(self, collection_id, item_id):
        g = get_graph()
        # get the URI for the Collection using the ID
        collection_uri = None
        for s in g.subjects(predicate=DCTERMS.identifier, object=Literal(collection_id)):
            collection_uri = s

        if collection_uri is None:
            return Response(
                "You have entered an unknown Collection ID",
                status=400,
                mimetype="text/plain"
            )

        # get URI
        uri = "https://w3id.org/dggs/tb16pix/zone/{}".format(item_id)
        print(uri)
        return FeatureRenderer(request, uri).render()

        # return Response(
        #     "The Feature you have entered the ID for is not part of the Collection you entered the ID for",
        #     status=400,
        #     mimetype="text/plain"
        # )


@api.route("/object")
class ObjectRoute(Resource):
    def get(self):
        return "nothing"


def render_api_error(title, status, message, mediatype="text/html"):
    if mediatype == "application/json":
        return jsonify({
            "title": title,
            "status": status,
            "message": message
        }), status
    elif mediatype in Renderer.RDF_MEDIA_TYPES:
        pass
    else:  # mediatype == "text/html":
        return render_template(
            "error.html",
            title=title,
            status=status,
            message=message
        ), status


if __name__ == "__main__":
    logging.basicConfig(
        filename=LOGFILE,
        level=logging.DEBUG,
        datefmt="%Y-%m-%d %H:%M:%S",
        format="%(asctime)s %(levelname)s %(filename)s:%(lineno)s %(message)s",
    )

    app.run(debug=DEBUG, threaded=True, port=PORT)
