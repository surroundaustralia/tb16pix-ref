from pyldapi import Renderer, ContainerRenderer
from typing import List
from .profiles import *
from api.config import *
from .link import *
from .collection import Collection
import json
from flask import Response, render_template
from flask_paginate import Pagination
from rdflib import URIRef
from rdflib.namespace import DCTERMS, RDF


class Collections:
    def __init__(self):
        self.collections = []
        g = get_graph()
        for s in g.subjects(predicate=RDF.type, object=OGCAPI.Collection):
            if (s, DCTERMS.isPartOf, URIRef(DATASET_URI)) in g:
                identifier = None
                title = None
                description = None
                for p, o in g.predicate_objects(subject=s):
                    if p == DCTERMS.identifier:
                        identifier = str(o)
                    elif p == DCTERMS.title:
                        title = str(o)
                    elif p == DCTERMS.description:
                        description = str(o)

                self.collections.append((str(s), identifier, title, description))


class CollectionsRenderer(ContainerRenderer):
    def __init__(self, request, other_links: List[Link] = None):
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

        self.page = (
            int(request.values.get("page")) if request.values.get("page") is not None else 1
        )
        self.per_page = (
            int(request.values.get("per_page"))
            if request.values.get("per_page") is not None
            else 20
        )
        # limit
        limit = int(request.values.get("limit")) if request.values.get("limit") is not None else None

        # if limit is set, ignore page & per_page
        if limit is not None:
            self.start = 0
            self.end = limit
        else:
            # generate list for requested page and per_page
            self.start = (self.page - 1) * self.per_page
            self.end = self.start + self.per_page

        collections = Collections().collections
        self.collections_count = len(collections)
        requested_collections = collections[self.start:self.end]

        super().__init__(
            request,
            LANDING_PAGE_URL + "/collections",
            "Collections",
            "The Collections of Features delivered by this OGC API instance",
            None,
            None,
            [(LANDING_PAGE_URL + "/collections/" + x[1], x[2]) for x in requested_collections],
            self.collections_count,
            profiles={"oai": profile_openapi},
            default_profile_token="oai"
        )

        self.ALLOWED_PARAMS = ["_profile", "_view", "_mediatype", "_format", "page", "per_page", "limit", "bbox"]

    def render(self):
        for v in self.request.values.items():
            if v[0] not in self.ALLOWED_PARAMS:
                return Response("The parameter {} you supplied is not allowed".format(v[0]), status=400)

        # try returning alt profile
        response = super().render()
        if response is not None:
            return response
        elif self.profile == "oai":
            if self.mediatype == "application/json":
                return self._render_oai_json()
            else:
                return self._render_oai_html()

    def _render_oai_json(self):
        page_json = {
            "links": [x.__dict__ for x in self.links],
            "collections": [x.to_dict() for x in self.collections]
        }

        return Response(
            json.dumps(page_json),
            mimetype=str(MediaType.JSON.value),
            headers=self.headers,
        )

    def _render_oai_html(self):
        pagination = Pagination(page=self.page, per_page=self.per_page, total=self.collections_count)

        _template_context = {
            "links": self.links,
            "collections": self.members,
            "pagination": pagination
        }

        return Response(
            render_template("collections_oai.html", **_template_context),
            headers=self.headers,
        )
