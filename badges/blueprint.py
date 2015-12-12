__author__ = "Jeremy Nelson"

import json
import requests
from flask import abort, Blueprint, jsonify, render_template, Response, request
from flask import redirect, url_for
from flask_negotiate import produces
from . import new_badge_class, issue_badge
from .forms import NewBadgeClass, NewAssertion
from .graph import *
       
    

open_badge = Blueprint("open_badge", __name__,
                       template_folder="templates")
open_badge.config = {}


@open_badge.record
def record_params(setup_state):
    app = setup_state.app
    open_badge.config = dict([(key, value) for (key,value) in app.config.items()])
    base_url = open_badge.config.get('ORGANIZATION').get('url')
    # Strip off trailing forward slash for TTL template
    if base_url.endswith("/"):
        base_url = base_url[:-1]
#    turtle_extension = render_template(
#        'klob_extension.ttl',
#        base_url=base_url)

def get_badge_classes():
    all_badges_response = requests.post(
       open_badge.config.get('TRIPLESTORE_URL'),
       data={"query": FIND_ALL_CLASSES,
             "format": "json"})
    if all_badges_response.status_code > 399:
        abort(502)
    bindings = all_badges_response.json().get('results').get('bindings')
    return [(r.get('altName')['value'], r.get('name')['value']) for r in bindings]
      

@open_badge.route("/Assertion/", methods=["POST", "GET"])
def add_badge_assertion():
    assertion_form = NewAssertion()
    assertion_form.badge.choices = get_badge_classes()
    if request.method.startswith("POST"):
        assertion_url = issue_badge(
            email=assertion_form.email.data,
            badge=assertion_form.badge.data,
            givenName=assertion_form.givenName.data,
            familyName=assertion_form.familyName.data,
            issuedOn=assertion_form.issuedOn.data,
            issuer=open_badge.config.get("ORGANIZATION")
            )
        uuid = assertion_url.split("/")[-1]
        redirect_url = url_for('open_badge.badge_assertion', uuid=uuid)
        print(uuid, redirect_url)
        redirect(redirect_url)
    return render_template(
        "assertion.html",
         form=assertion_form)

@open_badge.route("/Assertion/<uuid>")
@open_badge.route("/Assertion/<uuid>.json")
@produces('application/json', 'application/rdf+xml', 'text/html')
def badge_assertion(uuid):
    """Route returns individual badge assertion json or 404 error if not
    found in the repository.

    Args:
        event: Badge Type (Camp, Projects, Institutions, etc.)
        uid: Unique ID of the Badge

    Returns:
        Assertion JSON of issued badge
    """
    sparql = render_template(
        "jsonObjectQueryTemplate.rq",
        uri_sparql_select = """
            BIND ("{}" AS ?uid) .
            BIND (URI(CONCAT("http://localhost:8080/fedora/rest/",SUBSTR(?uid, 1,2),"/",SUBSTR(?uid, 3,2),
            "/",SUBSTR(?uid, 5,2),"/",SUBSTR(?uid, 7,2),"/",?uid)) AS ?uri) .""".format(uuid),
        object_type = "Assertion")
    assertion_response = requests.post( 
        open_badge.config.get('TRIPLESTORE_URL'),
        data={"query": sparql,
              "format": "json"})
    if assertion_response.status_code > 399:
        abort(505)
    raw_text = assertion_response.json().get('results').get('bindings')[0]['jsonString']['value']
    raw_text = "{" + raw_text + "}"
    return json.dumps(json.loads(raw_text),indent=4, sort_keys=True)


@open_badge.route("/BadgeClass/", methods=["POST", "GET"])
def add_badge_class():
    """Displays Form for adding a BadgeClass Form"""
    badge_class_form = NewBadgeClass()
    existing_badges = get_badge_classes()
    if request.method.startswith("POST"):
        print("Size of image {}".format(badge_class_form.image_file.raw_data))
        badge_url, badge_slug = new_badge_class(
            name=badge_class_form.name.data,
            description=badge_class_form.description.data,
            image=badge_class_form.image_file.data,
            startDate=badge_class_form.startDate.raw_data,
            endDate=badge_class_form.endDate.data,
            tags=badge_class_form.tags.data,
            issuer=open_badge.config.get("ORGANIZATION"),
            criteria=badge_class_form.criteria.data)
        redirect(url_for('open_badge.badge_class', badge_classname=badge_slug))
    return render_template(
        "badge_class.html",
        form=badge_class_form,
        badges=existing_badges)

    

@open_badge.route("/BadgeClass/<badge_classname>")
@open_badge.route("/BadgeClass/<badge_classname>.json")
@produces('application/json', 'application/rdf+xml', 'text/html')
def badge_class(badge_classname):
    """Route generates a JSON BadgeClass 
    <https://github.com/mozilla/openbadges-specification/> for each Islandora
    badge.

    Args:
        badge_classname: Name of Badge (Camp, Projects, Institutions, etc.)

    Returns:
        Badge Class JSON
    """
    sparql = render_template(
        "jsonObjectQueryTemplate.rq",
        uri_sparql_select = """?uri schema:alternativeName "{}"^^xsd:string .""".format(badge_classname),
        object_type = "BadgeClass") 
    badge_class_response = requests.post( 
        open_badge.config.get('TRIPLESTORE_URL'),
        data={"query": sparql,
              "format": "json"})
    if badge_class_response.status_code > 399:
        abort(505)
    raw_text = badge_class_response.json().get('results').get('bindings')[0]['jsonString']['value']
    raw_text = "{" + raw_text + "}"
    return "<pre>" + json.dumps(json.loads(raw_text),indent=4, sort_keys=True) +"</pre>"

@open_badge.route("/Criteria/<badge>")
@produces('application/json')
def badge_criteria(badge):
    """Route displays the criteria for the badge class

    Args:
        badge: Name of Badge (Camp, Projects, Institutions, etc.)

    Returns:
        JSON of badge's critera
    """
    event = badges.get(badge)
    badge_rdf = event.get('graph')
    badge_class_uri = event.get('uri')
    badge_criteria = {
        "name": "Criteria for {}".format(
            badge_rdf.value(
                subject=badge_class_uri,
                predicate=schema_namespace.name)),
        "educationalUse": [str(obj) for obj in badge_rdf.objects(
            subject=badge_class_uri, predicate=schema_namespace.educationalUse)]
    }
    return jsonify(badge_criteria)


@open_badge.route("/Issuer")
def badge_issuer_organization():
    "Route generates JSON for the badge issuer's organization"
    organization = {
        "name": badge_app.config['BADGE_ISSUER_NAME'],
        "url": badge_app.config['BADGE_ISSUER_URL']
    }
    return jsonify(organization)


@open_badge.route("/BadgeImage/<badge>.png")
@open_badge.route("/AssertionImage/<uid>.png")
def badge_image(badge=None, uid=None):
    if uid is not None:
        assertion_url = "http://localhost:8080/fedora/rest/{0}/{1}/{2}/{3}/{4}".format(
            uid[0:2], uid[2:4], uid[4:6], uid[6:8], uid)
        assertion_img_response = requests.post(
         open_badge.config.get('TRIPLESTORE_URL'),
            data={"query": FIND_IMAGE_SPARQL.format(assertion_url),
                  "format": "json"})
        if assertion_img_response.status_code > 399:
            abort(501)
        bindings = assertion_img_response.json().get('results').get('bindings')
        if len(bindings) < 1:
            abort(404)
        img_url = bindings[0]['image']['value']
        print(img_url)
    elif badge is not None:
        img_url = '/'.join(str(badges[badge]['url']).split("/")[:-1])
    else:
        abort(404)
    img_response = requests.get(img_url)
    if img_response.status_code > 399:
        abort(500)
    return Response(img_response.text, mimetype='image/png')

"""Test"""