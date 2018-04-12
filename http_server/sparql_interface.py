# bgp_interface.py
# Author: Thomas MINIER - MIT License 2017-2018
from flask import Blueprint, request, Response, render_template, abort, json
from query_engine.sage_engine import SageEngine
from query_engine.optimizer.plan_builder import build_query_plan
from http_server.utils import encode_saved_plan, decode_saved_plan, secure_url, format_marshmallow_errors
from time import time


def sparql_blueprint(datasets):
    """Get a Blueprint that implement a SPARQL interface with quota on /sparql/<dataset-name>"""
    sparql_blueprint = Blueprint('sparql-interface', __name__)

    @sparql_blueprint.route('/sparql/', methods=["GET"])
    def sparql_index():
        datasets_infos = datasets._config["datasets"]
        return render_template("index_sage.html", datasets=datasets_infos)

    @sparql_blueprint.route('/sparql/<dataset_name>', methods=['GET', 'POST'])
    def sparql_query(dataset_name):
        dataset = datasets.get_dataset(dataset_name)
        if dataset is None:
            abort(404)
        mimetype = request.accept_mimetypes.best_match(['application/json', 'text/html'])
        url = secure_url(request.url)
        engine = SageEngine()
        # process GET request as a single Triple Pattern BGP
        if request.method == "GET" or (not request.is_json):
            (subject, predicate, obj, offset, limit) = (
                request.args.get("subject", ""),
                request.args.get("predicate", ""),
                request.args.get("object", ""),
                request.args.get("offset", 0),
                request.args.get("limit", 0))
            (triples, cardinality) = dataset.search_triples(subject, predicate, obj, offset=int(offset), limit=int(limit))
            triples = list(triples)
            if mimetype is 'text/html':
                return render_template("sage.html", triples=triples, cardinality=cardinality)
            return json.jsonify(triples=triples, cardinality=cardinality)

        # else, process POST requests as SPARQL requests
        post_query = request.get_json()
        quota = int(request.args.get("quota", dataset.deadline())) / 1000
        next = decode_saved_plan(post_query['next']) if 'next' in post_query else None
        # build physical query plan, then execute it with the given number of tickets
        start = time()
        plan = build_query_plan(post_query['query'], dataset._factory, next)
        loadingTime = (time() - start) * 1000
        bindings, savedPlan, isDone = engine.execute(plan, quota)
        # compute controls for the next page
        start = time()
        nextPage = encode_saved_plan(savedPlan) if not isDone else None
        exportTime = (time() - start) * 1000
        stats = {'import': loadingTime, 'export': exportTime}
        return json.jsonify(bindings=bindings, pageSize=len(bindings), hasNext=not isDone, next=nextPage, stats=stats)
    return sparql_blueprint