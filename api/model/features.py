from pyldapi import Renderer, ContainerRenderer
from typing import List
from .profiles import *
from api.config import *
from .link import *
from .collection import Collection
from .feature import Feature
import json
from flask import Response, render_template
from flask_paginate import Pagination
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCAT, DCTERMS, RDF
import re


class FeaturesList:
    def __init__(self, request, collection_id):
        self.request = request
        self.page = (
            int(request.values.get("page")) if request.values.get("page") is not None else 1
        )
        self.per_page = (
            int(request.values.get("per_page"))
            if request.values.get("per_page") is not None
            else 20
        )
        # limit
        self.limit = int(request.values.get("limit")) if request.values.get("limit") is not None else None

        # if limit is set, ignore page & per_page
        if self.limit is not None:
            self.start = 0
            self.end = self.limit
        else:
            # generate list for requested page and per_page
            self.start = (self.page - 1) * self.per_page
            self.end = self.start + self.per_page

        g = get_graph()

        # get Collection
        for s in g.subjects(predicate=DCTERMS.identifier, object=Literal(collection_id)):
            self.collection = Collection(str(s))

        # get list of Features within this Collection
        features_uris = []
        # filter if we have a filtering param
        if request.values.get("bbox") is not None:
            # work out what sort of BBOX filter it is and filter by that type
            features_uris = self.get_feature_uris_by_bbox()
        else:
            # all features in list
            for s in g.subjects(predicate=DCTERMS.isPartOf, object=URIRef(self.collection.uri)):
                features_uris.append(s)

        self.feature_count = len(features_uris)
        # truncate the list of Features to this page
        page = features_uris[self.start:self.end]

        # Features - only this page's
        self.features = []
        for s in page:
            description = None
            for p, o in g.predicate_objects(subject=s):
                if p == DCTERMS.identifier:
                    identifier = str(o)
                elif p == DCTERMS.title:
                    title = str(o)
                elif p == DCTERMS.description:
                    description = str(o)
            self.features.append(
                (str(s), identifier, title, description)
            )

        self.bbox_type = None

    def get_feature_uris_by_bbox(self):
        allowed_bbox_formats = {
            "coords": r"([0-9\.\-]+),([0-9\.\-]+),([0-9\.\-]+),([0-9\.\-]+)",  # Lat Longs, e.g. 160.6,-55.95,-170,-25.89
            "cell_id": r"([A-Z][0-9]{0,15})$",  # single DGGS Cell ID, e.g. R1234
            "cell_ids": r"([A-Z][0-9]{0,15}),([A-Z][0-9]{0,15})",  # two DGGS cells, e.g. R123,R456
        }
        for k, v in allowed_bbox_formats.items():
            if re.match(v, self.request.values.get("bbox")):
                self.bbox_type = k

        if self.bbox_type is None:
            return None
        elif self.bbox_type == "coords":
            return self._get_filtered_features_list_bbox_wgs84()
        elif self.bbox_type == "cell_id":
            return self._get_filtered_features_list_bbox_dggs()
        elif self.bbox_type == "cell_ids":
            pass

    def _get_filtered_features_list_bbox_wgs84(self):
        parts = self.request.values.get("bbox").split(",")

        demo = """
            149.041411262992398 -35.292795884738389, 
            149.041411262992398 -35.141378579917053, 
            149.314863045854082 -35.141378579917053,
            149.314863045854082 -35.292795884738389,
            149.041411262992398 -35.292795884738389
            """

        q = """
            PREFIX dcterms: <http://purl.org/dc/terms/>
            PREFIX geo: <http://www.opengis.net/ont/geosparql#>
            PREFIX geof: <http://www.opengis.net/def/function/geosparql/>
            PREFIX ogcapi: <https://data.surroundaustralia.com/def/ogcapi/>

            SELECT ?f
            WHERE {{
                ?f a ogcapi:Feature ;
                   dcterms:isPartOf <{collection_uri}> ;            
                   geo:hasGeometry/geo:asWKT ?wkt .
    
                FILTER (geof:sfWithin(?wkt, 
                    '''
                    <http://www.opengis.net/def/crs/OGC/1.3/CRS84>
                    POLYGON ((
                        {tl_lon} {tl_lat}, 
                        {tl_lon} {br_lat}, 
                        {br_lon} {br_lat},
                        {br_lon} {tl_lat},
                        {tl_lon} {tl_lat}
                    ))
                    '''^^geo:wktLiteral))
            }}
            ORDER BY ?f
            """.format(**{
            "collection_uri": self.collection.uri,
            "tl_lon": parts[0],
            "tl_lat": parts[1],
            "br_lon": parts[2],
            "br_lat": parts[3]
        })
        features_uris = []
        for r in get_graph().query(q):
            features_uris.append(r["f"])

        return features_uris

    def _get_filtered_features_list_bbox_dggs(self):
        # # geo:sfIntersects - any Cell of the Feature is within the BBox
        # q = """
        #     PREFIX dcterms: <http://purl.org/dc/terms/>
        #     PREFIX geo: <http://www.opengis.net/ont/geosparql#>
        #     PREFIX geox: <https://linked.data.gov.au/def/geox#>
        #     PREFIX ogcapi: <https://data.surroundaustralia.com/def/ogcapi/>
        #
        #     SELECT ?f
        #     WHERE {{
        #         ?f a ogcapi:Feature ;
        #            dcterms:isPartOf <https://linked.data.gov.au/dataset/asgs2016/statisticalarealevel1/> .
        #         ?f geo:hasGeometry/geox:asDGGS ?dggs .
        #
        #         BIND (STRAFTER(STR(?dggs), "> ") AS ?coords)
        #
        #         FILTER CONTAINS(?coords, "{}")
        #     }}
        #     """.format(self.request.values.get("bbox"))
        # # TODO: update as RDFlib updates
        # # for r in get_graph().query(q):
        # #     features_uris.append((r["f"], r["prefLabel"]))
        # from SPARQLWrapper import SPARQLWrapper, JSON
        # sparql = SPARQLWrapper(SPARQL_ENDPOINT)
        # sparql.setQuery(q)
        # sparql.setReturnFormat(JSON)
        # ret = sparql.queryAndConvert()["results"]["bindings"]
        # return [URIRef(r["f"]["value"]) for r in ret]

        # geo:sfWithin - every Cell of the Feature is within the BBox
        q = """
            PREFIX dcterms: <http://purl.org/dc/terms/>
            PREFIX geo: <http://www.opengis.net/ont/geosparql#>
            PREFIX geox: <https://linked.data.gov.au/def/geox#>
            PREFIX ogcapi: <https://data.surroundaustralia.com/def/ogcapi/>            
            
            SELECT ?f ?coords
            WHERE {{
                ?f a ogcapi:Feature ;
                   dcterms:isPartOf <{}> .
                ?f geo:hasGeometry/geox:asDGGS ?dggs .
    
                BIND (STRAFTER(STR(?dggs), "> ") AS ?coords)
            }}
            """.format(self.collection.uri)
        from SPARQLWrapper import SPARQLWrapper, JSON
        sparql = SPARQLWrapper(SPARQL_ENDPOINT)
        sparql.setQuery(q)
        sparql.setReturnFormat(JSON)
        ret = sparql.queryAndConvert()["results"]["bindings"]
        feature_ids = []
        for r in ret:
            within = True
            for cell in r["coords"]["value"].split(" "):
                if not str(cell).startswith(self.request.values.get("bbox")):
                    within = False
                    break
            if within:
                feature_ids.append(URIRef(r["f"]["value"]))

        return feature_ids

    def _get_filtered_features_list_bbox_paging(self):
        pass


class Tb16PixFeaturesList(FeaturesList):
    def __init__(self, request, collection_id):
        self.request = request
        self.page = (
            int(request.values.get("page")) if request.values.get("page") is not None else 1
        )
        self.per_page = (
            int(request.values.get("per_page"))
            if request.values.get("per_page") is not None
            else 20
        )
        # limit
        self.limit = int(request.values.get("limit")) if request.values.get("limit") is not None else None

        # if limit is set, ignore page & per_page
        if self.limit is not None:
            self.start = 0
            self.end = self.limit
        else:
            # generate list for requested page and per_page
            self.start = (self.page - 1) * self.per_page
            self.end = self.start + self.per_page

        # get Collection
        g = get_graph()
        for s in g.subjects(predicate=DCTERMS.identifier, object=Literal(collection_id)):
            self.collection = Collection(str(s))

        # TB16Pix generates Features, it doesn't retrieve them from a DB

        # filter if we have a filtering param
        self.features = []
        if request.values.get("bbox") is not None:
            # work out what sort of BBOX filter it is and filter by that type
            self.features = self.get_feature_uris_by_bbox()
        else:
            # all features in this Grid
            for cell in TB16Pix.grid(int(collection_id[-1])):
                self.features.append((
                    "https://w3id.org/dggs/zone/{}".format(str(cell)),
                    str(cell),
                    "Zone {}".format(str(cell)),
                    None
                ))

        self.feature_count = len(self.features)
        # truncate the list of Features to this page
        self.features = self.features[self.start:self.end]

        self.bbox_type = None


class FeaturesRenderer(ContainerRenderer):
    def __init__(self, request, collection_id, other_links: List[Link] = None):
        self.request = request
        self.valid = self._valid_parameters()
        if self.valid[0]:
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

            self.feature_list = Tb16PixFeaturesList(request, collection_id)

            super().__init__(
                request,
                LANDING_PAGE_URL + "/collections/" + self.feature_list.collection.identifier + "/items",
                "Features",
                "The Features of Collection {}".format(self.feature_list.collection.identifier),
                None,
                None,
                [(LANDING_PAGE_URL + "/collections/" + self.feature_list.collection.identifier + "/items/" + x[1], x[2]) for x in self.feature_list.features],
                self.feature_list.collection.feature_count,
                profiles={"oai": profile_openapi, "geosp": profile_geosparql},
                default_profile_token="oai"
            )

    def _valid_parameters(self):
        allowed_params = ["_profile", "_view", "_mediatype", "_format", "page", "per_page", "limit", "bbox"]

        allowed_bbox_formats = [
            r"([0-9\.\-]+),([0-9\.\-]+),([0-9\.\-]+),([0-9\.\-]+)",  # Lat Longs, e.g. 160.6,-55.95,-170,-25.89
            r"([A-Z][0-9]{0,15})$",  # single DGGS Cell ID, e.g. R1234
            r"([A-Z][0-9]{0,15}),([A-Z][0-9]{0,15})",  # two DGGS cells, e.g. R123,R456
        ]

        for p in self.request.values.keys():
            if p not in allowed_params:
                return False, \
                       "The parameter {} you supplied is not allowed. " \
                       "For this API endpoint, you may only use one of '{}'".format(p, "', '".join(allowed_params)),

        if self.request.values.get("limit") is not None:
            try:
                int(self.request.values.get("limit"))
            except ValueError:
                return False, "The parameter 'limit' you supplied is invalid. It must be an integer"

        if self.request.values.get("bbox") is not None:
            for p in allowed_bbox_formats:
                if re.match(p, self.request.values.get("bbox")):
                    return True, None
            return False, "The parameter 'bbox' you supplied is invalid. Must be either two pairs of long/lat values, " \
                          "a DGGS Cell ID or a pair of DGGS Cell IDs"

        return True, None

    def render(self):
        # return without rendering anything if there is an error with the parameters
        if not self.valid[0]:
            return Response(
                self.valid[1],
                status=400,
                mimetype="text/plain"
            )

        # try returning alt profile
        response = super().render()
        if response is not None:
            return response

        elif self.profile == "oai":
            if self.mediatype == MediaType.JSON.value:
                return self._render_oai_json()
            elif self.mediatype == MediaType.GEOJSON.value:
                return self._render_oai_geojson()
            else:
                return self._render_oai_html()
        elif self.profile == "geosp":
            if self.mediatype == MediaType.HTML.value:
                return self._render_oai_html()
            else:
                return self._render_geosp_rdf()

    def _render_oai_json(self):
        page_json = {
            "links": [x.__dict__ for x in self.links],
            "collection": self.feature_list.collection.to_dict(),
        }

        return Response(
            json.dumps(page_json),
            mimetype=str(MediaType.JSON.value),
            headers=self.headers,
        )

    def _render_oai_geojson(self):
        page_json = {
            "links": [x.__dict__ for x in self.links],
            "collection": self.feature_list.collection.to_geo_json_dict(),
        }

        return Response(
            json.dumps(page_json),
            mimetype=str(MediaType.GEOJSON.value),
            headers=self.headers,
        )

    def _render_oai_html(self):
        pagination = Pagination(page=self.page, per_page=self.per_page, total=self.feature_list.feature_count)

        _template_context = {
            "links": self.links,
            "collection": self.feature_list.collection,
            "members": self.members,
            "pagination": pagination
        }

        if self.request.values.get("bbox") is not None:  # it it exists at this point, it must be valid
            _template_context["bbox"] = (self.feature_list.bbox_type, self.request.values.get("bbox"))

        return Response(
            render_template("features.html", **_template_context),
            headers=self.headers,
        )

    def _render_geosp_rdf(self):
        g = Graph()

        g = g + self.feature_list.collection.to_geosp_graph()

        for f in self.feature_list.features:
            g = g + Feature(f[0]).to_geosp_graph()

        # serialise in the appropriate RDF format
        if self.mediatype in ["application/rdf+json", "application/json"]:
            return Response(g.serialize(format="json-ld"), mimetype=self.mediatype)
        elif self.mediatype in Renderer.RDF_MEDIA_TYPES:
            return Response(g.serialize(format=self.mediatype), mimetype=self.mediatype)
        else:
            return Response(
                "The Media Type you requested cannot be serialized to",
                status=400,
                mimetype="text/plain"
            )
