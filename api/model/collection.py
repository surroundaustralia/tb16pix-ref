from typing import List
from .profiles import *
from api.config import *
from .link import *
import json
from flask import Response, render_template
from .spatial_object import SpatialExtent, TemporalExtent
from .feature import Feature
import markdown
from rdflib import URIRef, Literal
from rdflib.namespace import DCTERMS


class Collection(object):
    def __init__(
            self,
            uri: str,
            other_links: List[Link] = None,
    ):
        self.uri = uri
        g = get_graph()
        # Feature properties
        self.description = None
        for p, o in g.predicate_objects(subject=URIRef(self.uri)):
            if p == DCTERMS.title:
                self.title = str(o)
            elif p == DCTERMS.identifier:
                self.identifier = str(o)
            elif p == DCTERMS.description:
                self.description = markdown.markdown(str(o))

        # Collection other properties
        self.extent_spatial = None
        self.extent_temporal = None
        self.links = [
            Link(LANDING_PAGE_URL + "/collections/" + self.identifier + "/items",
                 rel=RelType.ITEMS.value,
                 type=MediaType.GEOJSON.value,
                 title=self.title)
        ]
        if other_links is not None:
            self.links.extend(other_links)

        self.feature_count = 0
        for s in g.subjects(predicate=DCTERMS.isPartOf, object=URIRef(self.uri)):
            self.feature_count += 1

    def to_dict(self):
        self.links = [x.__dict__ for x in self.links]

        delattr(self, "feature_count")  # this attribute is for internal use only and can be misleading if communicated
        return self.__dict__

    def to_geo_json_dict(self):
        self.links = [x.__dict__ for x in self.links]

        delattr(self, "feature_count")  # this attribute is for internal use only and can be misleading if communicated
        return self.__dict__

    def to_geosp_graph(self):
        g = Graph()
        g.bind("geo", GEO)
        g.bind("geox", GEOX)
        g.bind("dcterms", DCTERMS)

        c = URIRef(self.uri)

        g.add((
            c,
            RDF.type,
            DCTERMS.Collection
        ))

        g.add((
            c,
            DCTERMS.identifier,
            Literal(self.identifier)
        ))

        g.add((
            c,
            DCTERMS.title,
            Literal(self.title)
        ))

        g.add((
            c,
            DCTERMS.description,
            Literal(self.description)
        ))

        return g


class CollectionRenderer(Renderer):
    def __init__(self, request, collection_uri: str, other_links: List[Link] = None):
        self.collection = Collection(collection_uri)
        self.links = [
            Link(
                LANDING_PAGE_URL + "/collections.json",
                rel=RelType.SELF.value,
                type=MediaType.JSON.value,
                title="This Document"
            ),
            Link(
                LANDING_PAGE_URL + "/collections.html",
                rel=RelType.SELF.value,
                type=MediaType.HTML.value,
                title="This Document in HTML"
            ),
        ]
        if other_links is not None:
            self.links.extend(other_links)

        super().__init__(
            request,
            LANDING_PAGE_URL + "/collection/" + self.collection.identifier,
            profiles={"oai": profile_openapi},
            default_profile_token="oai"
        )

        self.ALLOWED_PARAMS = ["_profile", "_mediatype"]

    def render(self):
        for v in self.request.values.items():
            if v[0] not in self.ALLOWED_PARAMS:
                return Response("The parameter {} you supplied is not allowed".format(v[0]), status=400)

        # try returning alt profile
        response = super().render()
        if response is not None:
            return response
        elif self.profile == "oai":
            if self.mediatype == MediaType.JSON.value:
                return self._render_oai_json()
            else:
                return self._render_oai_html()

    def _render_oai_json(self):
        page_json = {
            "links": [x.__dict__ for x in self.links],
            "collection": self.collection.to_dict()
        }

        return Response(
            json.dumps(page_json),
            mimetype=str(MediaType.JSON.value),
            headers=self.headers,
        )

    def _render_oai_html(self):
        _template_context = {
            "links": self.links,
            "collection": self.collection
        }

        return Response(
            render_template("collection.html", **_template_context),
            headers=self.headers,
        )
