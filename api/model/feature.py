from typing import List
from .profiles import *
from api.config import *
from .link import *
import json
from flask import Response, render_template
from .spatial_object import SpatialExtent, TemporalExtent
from rdflib import URIRef, Literal
from rdflib.namespace import DCTERMS
from enum import Enum
from geomet import wkt
from geojson_rewind import rewind
import markdown


class GeometryRole(Enum):
    Area = "https://linked.data.gov.au/def/geometry-roles/area"
    Boundary = "https://linked.data.gov.au/def/geometry-roles/boundary"
    BoundingBox = "https://linked.data.gov.au/def/geometry-roles/bounding-box"
    BoundingCircle = "https://linked.data.gov.au/def/geometry-roles/bounding-circle"
    Concave = "https://linked.data.gov.au/def/geometry-roles/concave-hull"
    Convex = "https://linked.data.gov.au/def/geometry-roles/convex-hull"
    Centroid = "https://linked.data.gov.au/def/geometry-roles/centroid"
    Detailed = "https://linked.data.gov.au/def/geometry-roles/detailed"


class CRS(Enum):
    WGS84 = "http://www.opengis.net/def/crs/EPSG/0/4326"  # "http://epsg.io/4326"
    TB16PIX = "https://w3id.org/dggs/tb16pix"


class Geometry(object):
    def __init__(self, coordinates: str, role: GeometryRole, label: str, crs: CRS):
        self.coordinates = coordinates
        self.role = role
        self.label = label
        self.crs = crs

    def to_dict(self):
        return {
            "coordinates": self.coordinates,
            "role": self.role.value,
            "label": self.label,
            "crs": self.crs.value,
        }

    def to_geo_json_dict(self):
        # this only works for WGS84 coordinates, no differentiation on role for now
        if self.crs == CRS.WGS84:
            return wkt.loads(self.coordinates)
        else:
            return TypeError("Only WGS84 geometries can be serialised in GeoJSON")

    def to_html_wkt(self):
        return "<{}> {}".format(self.crs.value, self.coordinates)


class Feature(object):
    def __init__(
            self,
            uri: str,
            other_links: List[Link] = None,
    ):
        self.uri = uri

        q = """
            PREFIX dcterms: <http://purl.org/dc/terms/>
            PREFIX ogcapi: <https://data.surroundaustralia.com/def/ogcapi/>

            SELECT ?identifier ?title ?description
            WHERE {{
                ?uri a ogcapi:Feature ;
                   dcterms:isPartOf <{}> ;
                   dcterms:identifier ?identifier ;
                   OPTIONAL {{?uri dcterms:title ?title}}
                   OPTIONAL {{?uri dcterms:description ?description}}
            }}
            """  # .format(collection_id)
        g = get_graph()
        # Feature properties
        self.description = None
        for p, o in g.predicate_objects(subject=URIRef(self.uri)):
            if p == DCTERMS.identifier:
                self.identifier = str(o)
            elif p == DCTERMS.title:
                self.title = str(o)
            elif p == DCTERMS.description:
                self.description = markdown.markdown(str(o))
            elif p == DCTERMS.isPartOf:
                self.isPartOf = str(o)

        # Feature geometries
        # out of band call for Geometries as BNodes not supported by SPARQLStore
        q = """
            PREFIX geo: <http://www.opengis.net/ont/geosparql#>
            PREFIX geox: <https://linked.data.gov.au/def/geox#>
            SELECT * 
            WHERE {{
                <{}>
                    geo:hasGeometry/geo:asWKT ?g1 ;
                    geo:hasGeometry/geox:asDGGS ?g2 .
            }}
            """.format(self.uri)
        from SPARQLWrapper import SPARQLWrapper, JSON
        sparql = SPARQLWrapper(SPARQL_ENDPOINT)
        sparql.setQuery(q)
        sparql.setReturnFormat(JSON)
        ret = sparql.queryAndConvert()["results"]["bindings"]
        self.geometries = [
            Geometry(ret[0]["g1"]["value"], GeometryRole.Boundary, "WGS84 Geometry", CRS.WGS84),
            Geometry(ret[0]["g2"]["value"], GeometryRole.Boundary, "TB16Pix Geometry", CRS.TB16PIX),
        ]

        # Feature other properties
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

    def to_dict(self):
        self.links = [x.__dict__ for x in self.links]
        if self.geometries is not None:
            self.geometries = [x.to_dict() for x in self.geometries]
        return self.__dict__

    def to_geo_json_dict(self):
        # this only serialises the Feature properties and WGS84 Geometries
        """
        {
          "type": "Feature",
          "geometry": {
            "type": "LineString",
            "coordinates": [
              [102.0, 0.0], [103.0, 1.0], [104.0, 0.0], [105.0, 1.0]
            ]
          },
        """
        geojson_geometry = [g.to_geo_json_dict() for g in self.geometries if g.crs == CRS.WGS84][0]  # one only

        properties = {
            "title": self.title,
            "isPartOf": self.isPartOf
        }
        if self.description is not None:
            properties["description"] = self.description

        return {
            "id": self.uri,
            "type": "Feature",
            "geometry": rewind(geojson_geometry),
            "properties": properties
        }

    def to_geosp_graph(self):
        g = Graph()
        g.bind("geo", GEO)
        g.bind("geox", GEOX)

        f = URIRef(self.uri)
        g.add((
            f,
            RDF.type,
            GEO.Feature
        ))
        for geom in self.geometries:
            this_geom = BNode()
            g.add((
                f,
                GEO.hasGeometry,
                this_geom
            ))
            g.add((
                this_geom,
                RDFS.label,
                Literal(geom.label)
            ))
            g.add((
                this_geom,
                GEOX.hasRole,
                URIRef(geom.role.value)
            ))
            g.add((
                this_geom,
                GEOX.inCRS,
                URIRef(geom.crs.value)
            ))
            if geom.crs == CRS.TB16PIX:
                g.add((
                    this_geom,
                    GEOX.asDGGS,
                    Literal(geom.coordinates, datatype=GEOX.DggsLiteral)
                ))
            else:  # WGS84
                g.add((
                    this_geom,
                    GEO.asWKT,
                    Literal(geom.coordinates, datatype=GEO.WktLiteral)
                ))

        return g


class Tb16PixFeature(Feature):
    def __init__(
            self,
            uri: str,
            other_links: List[Link] = None,
    ):
        self.uri = uri

        # Feature properties
        # TB16Pix Dataset can translate a Feature (Zone) URI to an ID like this
        self.identifier = self.uri.split("/")[-1]
        self.title = "Zone {}".format(self.identifier)
        self.description = None
        self.isPartOf = "g{}".format(len(self.identifier))
        self.geometries = [
            Geometry(
                "POINT ({})".format(self.identifier),
                GeometryRole.Area,
                "TB16Pix Cell Geometry",
                CRS.TB16PIX
            ),
        ]

        from rhealpixdggs.dggs import Cell

        def _suid_from_string(zone_id):
            if len(zone_id) == 1:
                return [zone_id[0]]
            else:
                return [zone_id[0]] + [int(x) for x in zone_id[1:]]

        c = Cell(TB16Pix, _suid_from_string(self.identifier))
        centroid = c.nucleus(plane=False)
        self.geometries.append(
            Geometry(
                "POINT ({} {})".format(centroid[0], centroid[1]),
                GeometryRole.Centroid,
                "WGS84 Cell centroid",
                CRS.WGS84),
        )
        v = c.vertices(plane=False)

        self.geometries.append(
            Geometry(
                "POLYGON (({0}, {1}, {2}, {3}, {0}))".format(
                    "{} {}".format(v[0][0], v[0][1]),
                    "{} {}".format(v[1][0], v[1][1]),
                    "{} {}".format(v[2][0], v[2][1]),
                    "{} {}".format(v[3][0], v[3][1])
                ),
                GeometryRole.Boundary,
                "WGS84 Boundary",
                CRS.WGS84),
        )

        URI_BASE_ZONE = Namespace("https://w3id.org/dggs/tb16pix/zone/")

        def _calculate_parent(zone_id):
            if len(zone_id) == 1:
                return URI_BASE_ZONE + "Earth", "Earth"
            else:  # <LETTER>...<LETTER><0-8>*9
                return URI_BASE_ZONE + zone_id[:-1], zone_id[:-1]

        self.parent = _calculate_parent(self.identifier)

        def _calculate_children(zone_id):
            if len(zone_id) < 15:
                return [(URI_BASE_ZONE + zone_id + str(n), zone_id + str(n)) for n in range(9)]
            else:
                return None

        self.children = _calculate_children(self.identifier)

        def _calculate_neighbours(zone_id):
            c = Cell(TB16Pix, _suid_from_string(zone_id))
            neighbours = []
            for k, v in sorted(c.neighbors().items()):
                neighbours.append((k, str(v)))
            return neighbours

        self.neighbours = _calculate_neighbours(self.identifier)

        # Feature other properties
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


class FeatureRenderer(Renderer):
    def __init__(self, request, feature_uri: str, other_links: List[Link] = None):
        self.feature = Tb16PixFeature(feature_uri)
        self.links = []
        if other_links is not None:
            self.links.extend(other_links)

        super().__init__(
            request,
            LANDING_PAGE_URL + "/collections/" + self.feature.isPartOf + "/item/" + self.feature.identifier,
            profiles={"oai": profile_openapi, "geosp": profile_geosparql},
            default_profile_token="oai"
        )

        self.ALLOWED_PARAMS = ["_profile", "_view", "_mediatype"]

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
            elif self.mediatype == MediaType.GEOJSON.value:
                return self._render_oai_geojson()
            else:
                return self._render_oai_html()
        elif self.profile == "geosp":
            return self._render_geosp_rdf()

    def _render_oai_json(self):
        page_json = {
            "links": [x.__dict__ for x in self.links],
            "feature": self.feature.to_geo_json_dict()
        }

        return Response(
            json.dumps(page_json),
            mimetype=str(MediaType.JSON.value),
            headers=self.headers,
        )

    def _render_oai_geojson(self):
        page_json = self.feature.to_geo_json_dict()
        if len(self.links) > 0:
            page_json["links"] = [x.__dict__ for x in self.links]

        return Response(
            json.dumps(page_json),
            mimetype=str(MediaType.GEOJSON.value),
            headers=self.headers,
        )

    def _render_oai_html(self):
        _template_context = {
            "links": self.links,
            "feature": self.feature,
            "geometries": [(g.label, g.to_html_wkt()) for g in self.feature.geometries]
        }

        return Response(
            render_template("feature.html", **_template_context),
            headers=self.headers,
        )

    def _render_geosp_rdf(self):
        g = self.feature.to_geosp_graph()

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
